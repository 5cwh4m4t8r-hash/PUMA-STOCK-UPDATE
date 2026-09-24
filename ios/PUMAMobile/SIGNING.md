# PUMA Mobile — Apple 서명

실제 iPhone 설치용 IPA 서명은 Apple이 발급한 인증서와 프로비저닝 프로파일이 필요합니다.

저장소의 **Build Signed PUMA iPhone IPA** 워크플로는 다음 GitHub Actions Secrets를 사용합니다.

- `APPLE_TEAM_ID`
- `APPLE_CERTIFICATE_P12_BASE64`
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_PROVISIONING_PROFILE_BASE64`

## Ad Hoc 설치용

Apple Developer에서 다음이 필요합니다.

1. Bundle ID: `com.pumastock.mobile`
2. Apple Distribution 인증서
3. 설치할 iPhone의 UDID가 등록된 Ad Hoc 프로비저닝 프로파일
4. 인증서 private key가 포함된 `.p12`

파일은 GitHub에 직접 커밋하지 않습니다. 반드시 Actions Secret으로 저장합니다.

macOS에서 base64 변환:

```bash
base64 -i distribution.p12 | pbcopy
base64 -i PUMA_Mobile_AdHoc.mobileprovision | pbcopy
```

Windows PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("distribution.p12")) | Set-Clipboard
[Convert]::ToBase64String([IO.File]::ReadAllBytes("PUMA_Mobile_AdHoc.mobileprovision")) | Set-Clipboard
```

Secrets를 넣은 뒤 GitHub Actions에서 **Build Signed PUMA iPhone IPA**를 실행하고
`export_method = ad-hoc`을 선택하면 서명된 `PUMA_STOCK_MOBILE.ipa`가 생성됩니다.

## App Store / TestFlight

App Store Connect용 프로비저닝 프로파일을 Secret에 넣고
`export_method = app-store`로 실행합니다.

이 워크플로는 서명된 IPA 생성까지만 담당합니다.
TestFlight 자동 업로드는 별도 단계로 추가할 수 있습니다.

## 보안

- `.p12`, private key, App Store Connect `.p8` 파일을 저장소에 커밋하지 마세요.
- 비밀번호나 인증서 파일을 ChatGPT 메시지에 붙여 넣지 마세요.
- GitHub Actions는 임시 keychain을 만들고 빌드 종료 시 삭제합니다.
