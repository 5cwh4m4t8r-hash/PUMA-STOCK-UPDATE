# PUMA Relay

PUMA STOCK PRO의 외부망 모바일 중계서버입니다.

- 집 PC는 이 서버로 **outbound HTTPS** 요청만 보냅니다.
- 공유기 포트포워딩은 필요하지 않습니다.
- 서버는 최신 모바일 상태와 짧은 명령 큐만 메모리에 보관합니다.
- 계좌 App Key / Secret은 중계서버로 전송하지 않습니다.
- 실제 주문은 항상 집 PC의 기존 PUMA 주문 경로에서 실행됩니다.

## 실행

```bash
docker build -t puma-relay .
docker run --rm -p 8787:8787 puma-relay
```

실사용에서는 Render/Fly.io/VPS+Caddy/Nginx 등으로 **HTTPS**를 붙이세요.
PC PUMA의 모바일 연동 탭에는 최종 HTTPS 주소(예: `https://puma-relay.example.com`)를 입력합니다.

## API

PC:
- `POST /v1/pc/register`
- `POST /v1/pc/state`
- `GET /v1/pc/commands`
- `POST /v1/pc/result/<id>`

iPhone:
- `GET /v1/mobile/state`
- `POST /v1/mobile/command`
- `GET /v1/mobile/command/<id>`

모바일 인증은 12자리 Device ID + PC에서 발급한 6자리 연결코드입니다.
실패 인증은 IP+Device 기준으로 제한됩니다.
