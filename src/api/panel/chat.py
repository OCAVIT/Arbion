"""Manager panel chat API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import io
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_manager
from src.db import get_db
from src.models import (
    AuditAction,
    DealStatus,
    DetectedDeal,
    LedgerEntry,
    MessageRole,
    MessageTarget,
    Negotiation,
    NegotiationMessage,
    NegotiationStage,
    OutboxMessage,
    User,
)
from src.schemas.copilot import SuggestedResponses
from src.schemas.deal import DealCloseRequest, MessageResponse, SendMessageRequest
from src.services.ai_copilot import copilot


class NotesRequest(BaseModel):
    """Request to update deal notes."""
    notes: str = Field(..., max_length=2000)
from src.utils.audit import get_client_ip, log_action

router = APIRouter(prefix="/chat")
templates = Jinja2Templates(directory="src/templates")


@router.get("/{negotiation_id}", response_class=HTMLResponse, include_in_schema=False)
async def chat_page(
    request: Request,
    negotiation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Render chat page for a negotiation.

    SECURITY: Verifies manager has access to this deal.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK: Manager can only access their assigned deals
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.VIEW_DEAL,
        target_type="negotiation",
        target_id=negotiation_id,
        ip_address=get_client_ip(request),
    )

    return templates.TemplateResponse(
        "panel/chat.html",
        {
            "request": request,
            "user": current_user,
            "negotiation_id": negotiation_id,
            "deal": negotiation.deal,
        },
    )


@router.get("/{negotiation_id}/messages")
async def get_messages(
    negotiation_id: int,
    target: Optional[str] = Query(None, pattern="^(seller|buyer)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Get chat messages for a negotiation.

    SECURITY:
    - Verifies manager has access
    - Masks sensitive data (phones, usernames) in messages
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    # Build query
    query = (
        select(NegotiationMessage)
        .options(selectinload(NegotiationMessage.sent_by))
        .where(NegotiationMessage.negotiation_id == negotiation_id)
    )

    if target:
        target_enum = MessageTarget.SELLER if target == "seller" else MessageTarget.BUYER
        query = query.where(NegotiationMessage.target == target_enum)

    query = query.order_by(NegotiationMessage.created_at)

    msg_result = await db.execute(query)
    messages = msg_result.scalars().all()

    # Build telegram_message_id -> message lookup for reply resolution
    tg_id_to_msg = {}
    for msg in messages:
        if msg.telegram_message_id:
            tg_id_to_msg[msg.telegram_message_id] = msg

    def _get_reply_info(msg):
        if not msg.reply_to_message_id:
            return None
        original = tg_id_to_msg.get(msg.reply_to_message_id)
        if not original:
            return None
        if original.role == MessageRole.SELLER:
            name = "Продавец"
        elif original.role == MessageRole.BUYER:
            name = "Покупатель"
        elif original.role == MessageRole.MANAGER:
            name = original.sent_by.display_name if original.sent_by else "Менеджер"
        elif original.role == MessageRole.AI:
            name = "Ассистент"
        else:
            name = "Система"
        content = original.content or ""
        if len(content) > 100:
            content = content[:100] + "..."
        return {"content": content, "sender_name": name}

    all_messages = [
        MessageResponse.from_message(
            msg,
            role="manager",  # This triggers masking
            sender_name=msg.sent_by.display_name if msg.sent_by else None,
            reply_info=_get_reply_info(msg),
        )
        for msg in messages
    ]

    deal = negotiation.deal

    # Common deal details for manager
    deal_details = {
        "deal_status": deal.status.value,
        "product": deal.product,
        "sell_price": str(deal.sell_price),
        "region": deal.region,
        "seller_condition": deal.seller_condition,
        "seller_city": deal.seller_city,
        "seller_specs": deal.seller_specs,
        "notes": deal.notes,
        "ai_insight": deal.ai_insight,
    }

    # If no target filter, return separated lists
    if not target:
        seller_messages = [m for m in all_messages if m.target == "seller"]
        buyer_messages = [m for m in all_messages if m.target == "buyer"]
        return {
            "messages": all_messages,
            "seller_messages": seller_messages,
            "buyer_messages": buyer_messages,
            **deal_details,
        }

    return {
        "messages": all_messages,
        **deal_details,
    }


@router.post("/{negotiation_id}/send")
async def send_message(
    request: Request,
    negotiation_id: int,
    data: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Send a message in the negotiation to seller or buyer.

    Message is queued for sending via Telegram.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    # Check deal is not closed
    if negotiation.deal.status in [DealStatus.WON, DealStatus.LOST]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка уже закрыта",
        )

    # Determine target
    target_enum = MessageTarget.SELLER if data.target == "seller" else MessageTarget.BUYER

    # Add message to history
    message = NegotiationMessage(
        negotiation_id=negotiation_id,
        role=MessageRole.MANAGER,
        target=target_enum,
        content=data.content,
        sent_by_user_id=current_user.id,
    )
    db.add(message)

    # Determine recipient based on target
    if data.target == "seller":
        recipient_id = negotiation.seller_sender_id
    else:
        # Buyer - use buyer_sender_id from deal
        recipient_id = negotiation.deal.buyer_sender_id
        if not recipient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Контакт покупателя недоступен",
            )

    # Queue for sending via Telegram
    outbox = OutboxMessage(
        recipient_id=recipient_id,
        message_text=data.content,
        negotiation_id=negotiation_id,
        sent_by_user_id=current_user.id,
    )
    db.add(outbox)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.SEND_MESSAGE,
        target_type="negotiation",
        target_id=negotiation_id,
        ip_address=get_client_ip(request),
    )

    await db.commit()
    await db.refresh(message)

    return {
        "success": True,
        "message_id": message.id,
        "message": MessageResponse.from_message(
            message,
            role="manager",
            sender_name=current_user.display_name,
        ),
    }


@router.post("/{negotiation_id}/notes")
async def update_notes(
    request: Request,
    negotiation_id: int,
    data: NotesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Update deal notes (manager)."""
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Переговоры не найдены")

    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="У вас нет доступа к этой сделке")

    negotiation.deal.notes = data.notes

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.UPDATE_DEAL,
        target_type="deal",
        target_id=negotiation.deal.id,
        action_metadata={"action": "update_notes"},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}


@router.post("/{negotiation_id}/close")
async def close_deal(
    request: Request,
    negotiation_id: int,
    data: DealCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Close a deal as won or lost.

    SECURITY: Manager cannot see profit - ledger entry is created
    by the system/owner.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    deal = negotiation.deal

    # Check deal is not already closed
    if deal.status in [DealStatus.WON, DealStatus.LOST]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка уже закрыта",
        )

    # Update status
    deal.status = DealStatus.WON if data.status == "won" else DealStatus.LOST
    deal.ai_resolution = data.resolution

    # Update negotiation stage
    negotiation.stage = NegotiationStage.CLOSED

    # Create ledger entry for won deals
    # Note: Profit calculation - manager doesn't see this
    if deal.status == DealStatus.WON:
        profit = deal.margin
        deal.profit = profit

        # Calculate manager commission
        manager_commission = Decimal("0")
        manager = await db.get(User, current_user.id)
        if manager and manager.commission_rate:
            manager_commission = deal.margin * manager.commission_rate

        ledger = LedgerEntry(
            deal_id=deal.id,
            buy_amount=deal.buy_price,
            sell_amount=deal.sell_price,
            profit=profit,
            closed_by_user_id=current_user.id,
            manager_commission=manager_commission,
        )
        db.add(ledger)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.CLOSE_DEAL,
        target_type="deal",
        target_id=deal.id,
        action_metadata={"status": data.status, "resolution": data.resolution},
        ip_address=get_client_ip(request),
    )

    await db.commit()

    return {
        "success": True,
        "message": "Сделка закрыта" if data.status == "won" else "Сделка отменена",
    }


@router.get("/{negotiation_id}/suggestions", response_model=SuggestedResponses)
async def get_suggestions(
    negotiation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Get AI-suggested response variants for the current negotiation."""
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    # Get last message from counterparty
    last_msg_result = await db.execute(
        select(NegotiationMessage)
        .where(
            NegotiationMessage.negotiation_id == negotiation_id,
            NegotiationMessage.role != MessageRole.MANAGER,
        )
        .order_by(NegotiationMessage.created_at.desc())
        .limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()
    last_text = last_msg.content if last_msg else ""

    variants = await copilot.suggest_responses(negotiation_id, last_text, db)

    # Build margin info if deal has data
    deal = negotiation.deal
    margin_info = None
    if deal.margin and deal.sell_price and deal.sell_price > 0:
        margin_pct = float(deal.margin / deal.sell_price * 100)
        margin_info = f"Текущая маржа: {float(deal.margin):.0f}₽ ({margin_pct:.1f}%)"

    return SuggestedResponses(
        variants=variants if variants else [],
        margin_info=margin_info,
    )


@router.get("/{negotiation_id}/media/{message_id}")
async def get_media(
    negotiation_id: int,
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Proxy media (photo/video/document) from Telegram.

    Downloads on-demand from Telegram using stored telegram_message_id,
    streams to browser. No server-side file storage.
    Browser caching via Cache-Control header avoids repeated downloads.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Переговоры не найдены")

    # SECURITY CHECK
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="У вас нет доступа")

    # Get the message
    msg_result = await db.execute(
        select(NegotiationMessage).where(
            NegotiationMessage.id == message_id,
            NegotiationMessage.negotiation_id == negotiation_id,
        )
    )
    message = msg_result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено")

    if not message.media_type or not message.telegram_message_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не содержит медиа")

    # Determine chat entity based on message role/target
    from src.services.telegram_client import get_telegram_service

    telegram = get_telegram_service()
    if not telegram or not telegram.client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram недоступен")

    # Determine which chat to fetch from
    if message.target == MessageTarget.SELLER:
        entity_id = negotiation.seller_sender_id
    else:
        entity_id = negotiation.deal.buyer_sender_id

    if not entity_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Контакт недоступен")

    try:
        # Fetch the message from Telegram to get fresh file reference
        entity = await telegram.client.get_entity(entity_id)
        tg_messages = await telegram.client.get_messages(entity, ids=message.telegram_message_id)

        if not tg_messages:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение удалено в Telegram")

        tg_msg = tg_messages

        # Download media bytes
        media_bytes = await telegram.client.download_media(tg_msg, bytes)

        if not media_bytes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Медиа недоступно")

        # Determine content type
        content_type_map = {
            "photo": "image/jpeg",
            "video": "video/mp4",
            "sticker": "image/webp",
        }
        content_type = content_type_map.get(message.media_type, "application/octet-stream")

        # For documents, try to get mime_type from Telegram
        if message.media_type == "document" and hasattr(tg_msg, 'document') and tg_msg.document:
            content_type = getattr(tg_msg.document, 'mime_type', None) or "application/octet-stream"

        headers = {"Cache-Control": "private, max-age=3600"}

        # Add Content-Disposition for documents (show filename, allow inline PDF viewing)
        if message.media_type == "document":
            fname = message.file_name
            if not fname and hasattr(tg_msg, 'document') and tg_msg.document:
                try:
                    from telethon.tl.types import DocumentAttributeFilename
                    for attr in (tg_msg.document.attributes or []):
                        if isinstance(attr, DocumentAttributeFilename):
                            fname = attr.file_name
                            break
                except Exception:
                    pass
            if fname:
                # Use inline so PDFs open in browser, with filename for download
                from urllib.parse import quote
                headers["Content-Disposition"] = f'inline; filename="{quote(fname)}"'

        return StreamingResponse(
            io.BytesIO(media_bytes),
            media_type=content_type,
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Media download error for msg #{message_id}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Ошибка загрузки медиа из Telegram")


# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.txt', '.csv', '.rtf', '.odt', '.ods',
    # Archives
    '.zip', '.rar', '.7z',
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_DIR = os.path.join("uploads", "outbox")


@router.post("/{negotiation_id}/send-file")
async def send_file(
    request: Request,
    negotiation_id: int,
    file: UploadFile = File(...),
    target: str = Form(..., pattern="^(seller|buyer)$"),
    caption: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Send a file (photo/document) in the negotiation to seller or buyer.

    File is saved temporarily and queued for sending via Telegram.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Переговоры не найдены")

    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="У вас нет доступа к этой сделке")

    if negotiation.deal.status in [DealStatus.WON, DealStatus.LOST]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сделка уже закрыта")

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не выбран")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый тип файла: {ext}",
        )

    # Read file content and check size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл слишком большой (макс. {MAX_FILE_SIZE // (1024*1024)} МБ)",
        )

    # Determine media type
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    media_type = "photo" if ext in image_extensions else "document"

    # Save file to temp directory
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    with open(file_path, "wb") as f:
        f.write(file_content)

    # Determine target
    target_enum = MessageTarget.SELLER if target == "seller" else MessageTarget.BUYER

    # Build content text
    content = caption.strip() if caption and caption.strip() else (
        f"[{file.filename}]" if media_type == "document" else "[фото]"
    )

    # Save to chat history
    message = NegotiationMessage(
        negotiation_id=negotiation_id,
        role=MessageRole.MANAGER,
        target=target_enum,
        content=content,
        sent_by_user_id=current_user.id,
        media_type=media_type,
        file_name=file.filename if media_type == "document" else None,
    )
    db.add(message)

    # Determine recipient
    if target == "seller":
        recipient_id = negotiation.seller_sender_id
    else:
        recipient_id = negotiation.deal.buyer_sender_id
        if not recipient_id:
            # Clean up temp file
            os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Контакт покупателя недоступен",
            )

    # Queue for sending
    outbox = OutboxMessage(
        recipient_id=recipient_id,
        message_text=caption.strip() or None,
        negotiation_id=negotiation_id,
        sent_by_user_id=current_user.id,
        media_type=media_type,
        media_file_path=file_path,
        file_name=file.filename,
    )
    db.add(outbox)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.SEND_MESSAGE,
        target_type="negotiation",
        target_id=negotiation_id,
        action_metadata={"type": "file", "filename": file.filename},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    await db.refresh(message)

    return {
        "success": True,
        "message_id": message.id,
        "message": MessageResponse.from_message(
            message,
            role="manager",
            sender_name=current_user.display_name,
        ),
    }
