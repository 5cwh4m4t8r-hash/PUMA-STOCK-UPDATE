PUMA STOCK PRO v2.9.4 CLEAN -> v2.9.5 업데이트 기능 활성화

사용법:
1. 이 ZIP 안의 두 파일을 현재 PUMA 프로그램 최상위 폴더에 넣습니다.
   - PUMA_UPDATE_ENABLE.bat
   - PUMA_UPDATE_ENABLE.py
2. PUMA가 실행 중이면 먼저 종료합니다.
3. PUMA_UPDATE_ENABLE.bat 를 한 번만 더블클릭합니다.
4. v2.9.5 적용 후 PUMA가 다시 실행됩니다.

그 이후:
PUMA 내부의 업데이트 탭에서
[업데이트 확인] -> [업데이트 적용]
만 사용하면 됩니다.

보안:
- 서버 manifest의 SHA256과 다운로드 파일을 반드시 비교합니다.
- VBS/PowerShell 사용 안 함.
- 별도 DETACHED_PROCESS 업데이트 워커 사용 안 함.
- 기존 파일은 _bootstrap_backup_v2.9.4 폴더에 백업합니다.
