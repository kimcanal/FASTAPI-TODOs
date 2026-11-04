# JMeter 실행 이미지 (multi-arch: amd64 / arm64 모두 동작)
#
# 베이스 이미지: Docker 공식 openjdk 이미지는 2022년 7월 deprecated 되어 더 이상 보안 패치를
# 받지 않는다. 공식 대체재인 eclipse-temurin으로 교체. temurin은 멀티아키 이미지라
# arm64v8/ 접두사로 아키텍처를 고정할 필요가 없다. JMeter 5.6.3은 Java 8+에서 동작하고 17+ 권장.
FROM eclipse-temurin:17-jre-jammy

# JMeter 5.4.1은 log4j-core 2.13.3을 번들해 Log4Shell(CVE-2021-44228)에 노출된다.
# 부하 테스트 도구는 응답 헤더/본문을 로깅하므로 실제로 악용 가능한 경로. 최신 안정 버전 사용.
ENV JMETER_VERSION=5.6.3
ENV JMETER_HOME=/opt/apache-jmeter-${JMETER_VERSION}
ENV PATH=${JMETER_HOME}/bin:$PATH

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 다운로드 무결성 검증 — 검증 없는 다운로드는 미러 변조/중간자 공격에 무방비.
RUN set -eux; \
    cd /tmp; \
    curl -fsSL -o jmeter.tgz    "https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz"; \
    curl -fsSL -o jmeter.sha512 "https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz.sha512"; \
    EXPECTED="$(tr -d ' \n' < jmeter.sha512 | sed 's/.*://' | grep -oE '[0-9a-fA-F]{128}' | head -1 | tr 'A-Z' 'a-z')"; \
    ACTUAL="$(sha512sum jmeter.tgz | cut -d' ' -f1)"; \
    [ "$EXPECTED" = "$ACTUAL" ] || { echo "checksum mismatch: $ACTUAL != $EXPECTED"; exit 1; }; \
    tar -xzf jmeter.tgz -C /opt/; \
    rm -f jmeter.tgz jmeter.sha512

# InfluxDB 백엔드 리스너가 쓰는 플러그인 jar — JMeter 5.6.3 코어에 이미 포함되어 있으므로 추가 설치 불필요
# (org.apache.jmeter.visualizers.backend.influxdb.InfluxdbBackendListenerClient)

# 비(非)root 실행 — 부하 테스트를 root로 돌릴 이유가 없다. 컨테이너 탈출 시 피해 범위를 줄인다.
# uid 1000은 Ubuntu 기본 사용자와 맞춰 bind mount 쓰기 권한 문제를 피하기 위한 값.
RUN useradd -u 1000 -m -s /bin/bash jmeter && \
    mkdir -p /jmeter && chown -R jmeter:jmeter /jmeter ${JMETER_HOME}

USER jmeter

# 작업 디렉터리를 버전과 무관한 /jmeter로 고정 — 버전을 올릴 때마다 경로를 고칠 필요가 없다.
WORKDIR /jmeter

CMD ["jmeter", "-n"]
