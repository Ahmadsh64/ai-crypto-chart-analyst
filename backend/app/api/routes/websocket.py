"""Frontend market + historical replay WebSocket endpoints."""

from fastapi import APIRouter, WebSocket

from app.core.config import get_settings
from app.core.security import authenticate_websocket
from app.market_data.websocket_manager import get_websocket_manager
from app.replay.ws_hub import get_replay_ws_hub

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/market")
async def market_websocket(websocket: WebSocket) -> None:
    """
    Real-time market stream for the dashboard.

    When AUTH_ENABLED=true, clients must connect with ``?access_token=<jwt>``.

    Client -> server:
      {"action":"subscribe","exchange":"binance","symbol":"BTC/USDT","market_type":"spot","timeframe":"15m"}
      {"action":"subscribe","exchange":"binance","symbol":"ETH/USDT","market_type":"spot","ticker_only":true}
      {"action":"unsubscribe","exchange":"binance","symbol":"BTC/USDT","market_type":"spot","timeframe":"15m"}
      {"action":"ping"}

    Server -> client message types:
      ticker_update | trade_update | candle_update | connection_status |
      subscription_error | subscribed | unsubscribed
    """
    user = await authenticate_websocket(websocket)
    if get_settings().auth_enabled and user is None:
        return
    await get_websocket_manager().handle_client(websocket)


@router.websocket("/ws/replay")
async def replay_websocket(websocket: WebSocket) -> None:
    """
    Historical replay channel (Phase 5.1) — never mixed with live market streams.

    When AUTH_ENABLED=true, clients must connect with ``?access_token=<jwt>``.

    Client -> server:
      {"action":"subscribe","session_id":"rp_..."}
      {"action":"unsubscribe"}
      {"action":"ping"}

    Server -> client:
      replay_connected | replay_subscribed | replay_unsubscribed | pong |
      replay_started | replay_paused | replay_resumed | replay_stopped |
      replay_reset | replay_candle_update | replay_candle_closed |
      replay_snapshot | replay_completed | replay_error |
      replay_analysis_update | replay_analysis_error
    """
    user = await authenticate_websocket(websocket)
    if get_settings().auth_enabled and user is None:
        return
    await get_replay_ws_hub().handle_client(websocket)
