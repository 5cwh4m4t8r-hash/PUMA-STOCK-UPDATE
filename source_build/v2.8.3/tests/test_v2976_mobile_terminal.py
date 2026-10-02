from pathlib import Path


def test_mobile_terminal_redesign_keeps_core_controls_and_ids():
    src = Path("puma_trader/mobile_bridge.py").read_text(encoding="utf-8")
    required = [
        'class="hero-card"',
        'id="homeAutoStatus"',
        'id="homeSeed"',
        'id="homeRisk"',
        'id="candidateList"',
        'id="chartCanvas"',
        'id="autoStartBtn"',
        'id="autoStopBtn"',
        'id="orderBtn"',
        'id="unlockLiveBtn"',
        'id="lockLiveBtn"',
        'id="autoStatusOrb"',
        'PUMA STOCK <span>PRO</span>',
        '가보자 고정 매매 규칙 보기',
        '수동 주문 열기',
    ]
    for text in required:
        assert text in src


def test_mobile_terminal_uses_pwa_cache_v2_and_new_icon():
    src = Path("puma_trader/mobile_bridge.py").read_text(encoding="utf-8")
    assert "const CACHE='puma-mobile-v2';" in src
    assert '<path d="M170 354V158h103' in src
    assert '"background_color": "#070a0f"' in src
    assert '"theme_color": "#070a0f"' in src


def test_mobile_redesign_does_not_change_auto_command_contract():
    src = Path("puma_trader/mobile_bridge.py").read_text(encoding="utf-8")
    start = src[src.index("async function startAuto()"):src.index("async function stopAuto()")]
    assert "candidate_source:(scope==='ALL'?'HERO4'" in start
    assert "order_budget:" not in start
    assert "max_positions:" not in start
    assert "if(autoCommandBusy)return;" in src
    assert "setInterval(check,150)" in src
