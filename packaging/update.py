# 사내 Nexus 레포지토리에 빌드된 파일을 업로드하는 스크립트 (가상 적용).

import os

from dotenv import load_dotenv

from backend.core.config import _project_root

load_dotenv(dotenv_path=_project_root() / ".env", override=False)

NexusBaseUrl = os.getenv("NEXUS_BASE_URL")
NexusUsername = os.getenv("NEXUS_USERNAME")
NexusPass = os.getenv("NEXUS_PASSWORD")

print("exe 업로드 중...")
print("exe 업로드 완료")

print("latest.json 업로드 중...")
print("latest.json 업로드 완료")
