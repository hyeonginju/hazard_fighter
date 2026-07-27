FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations

# --proxy-headers: 클라우드는 앞에 로드밸런서가 있어 서버는 http 로 요청을 받는다.
#   이 옵션이 없으면 X-Forwarded-Proto 를 무시해 OAuth 리다이렉트 주소를 http:// 로
#   만들고, 콘솔에 등록된 https 주소와 불일치해 로그인이 깨진다 (터널에서 실제로 겪음).
# --forwarded-allow-ips: --proxy-headers 만으로는 부족하다. uvicorn 은 신뢰 목록
#   (기본 127.0.0.1)에서 온 X-Forwarded-* 만 반영하는데, 컨테이너 밖 프록시의 IP 는
#   127.0.0.1 이 아니다. 로컬 터널은 localhost 에서 붙어서 우연히 통했지만 Cloud Run 은
#   프록시 IP 가 다르므로 그대로 두면 배포 후 로그인이 깨진다 (컨테이너 테스트로 확인).
#   "*" 는 "앞단 프록시를 신뢰한다"는 선언 — Cloud Run 처럼 플랫폼 LB 만 컨테이너에
#   닿을 수 있는 환경에서 유효하다. 컨테이너가 외부에 직접 노출되는 환경이면 좁혀야 한다.
# ${PORT:-8000}: Cloud Run 등은 포트를 환경변수로 주입한다. 로컬/compose 는 8000.
# 마이그레이션은 여기서 돌리지 않는다 — 컨테이너가 자주 새로 뜨는 서버리스에서 매 기동마다
#   alembic 을 돌리면 콜드 스타트가 느려지고, 인스턴스 여러 개가 동시에 DDL 을 걸 수 있다.
#   배포 시 한 번만 별도로 실행한다 (README 배포 절차 참고).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-*}"]
