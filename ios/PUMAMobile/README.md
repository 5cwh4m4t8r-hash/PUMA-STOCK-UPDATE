# PUMA STOCK Mobile (iPhone)

PUMA STOCK PRO의 네이티브 SwiftUI 모바일 앱입니다.

## 기능

- PC/KIWOOM 연결 상태
- 조건검색 후보
- 현재 종목 및 일봉/5분봉 차트
- EMA112/224/448, 4종 화살표, 수박 표시
- 단타 / 스윙 / 밥3 분석
- 보유종목
- 자동매매 시작/중지
- 실전 잠금
- 시장가/지정가/스톱지정가 주문

실제 매매는 iPhone에서 직접 키움 API를 호출하지 않습니다.
모든 명령은 집 PC의 기존 PUMA 주문 경로를 통해 실행됩니다.

## 연결 방법 A — Direct / Tailscale

가장 간단한 외부망 연결입니다.

1. PC와 iPhone에 Tailscale을 설치하고 같은 tailnet에 로그인합니다.
2. PC PUMA의 **모바일 연동 → 모바일 LAN 서버 시작**을 누릅니다.
3. PC에서 다음을 실행합니다.

```powershell
tailscale serve --bg 8765
tailscale serve status
```

4. 출력된 `https://...ts.net` 주소를 PUMA Mobile의 **Direct / Tailscale** 주소에 저장합니다.
5. PC PUMA에 표시된 6자리 연결코드를 입력합니다.

이 방식은 같은 Wi-Fi가 아니어도 되고, iPhone이 5G/LTE여도 됩니다.
Tailscale Serve는 tailnet 내부에만 공개됩니다.

## 연결 방법 B — Relay

공개 HTTPS Relay 서버를 사용할 경우:

1. `/relay`의 Docker 이미지를 HTTPS 호스팅에 배포합니다.
2. PC PUMA의 모바일 연동 탭에 Relay HTTPS 주소를 입력합니다.
3. **외부망 연결**을 누릅니다.
4. iPhone 앱에서:
   - 연결 방식: Relay
   - Relay HTTPS 주소
   - PC에 표시된 12자리 PUMA 기기 ID
   - 6자리 연결코드
   를 저장합니다.

집 공유기 포트포워딩은 필요하지 않습니다.

## Xcode 프로젝트 생성

XcodeGen 사용:

```bash
cd ios/PUMAMobile
xcodegen generate
open PUMAMobile.xcodeproj
```

실제 iPhone 설치에는 Apple 코드서명이 필요합니다.
개인 개발/테스트는 Xcode의 Automatic Signing을 사용하면 됩니다.
