# The game (#112, decision 3). The C game's image is tools/oracle/Dockerfile.c at the c-final tag.
#   docker build -t charm .
FROM ubuntu:26.04
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --no-create-home --home-dir /opt/charm charm
WORKDIR /opt/charm
# The game, its areas and data dirs, plus the README, credits and licence files every copy must keep (see
# README.md, Licence terms).
COPY game/charm/ game/charm/
COPY area/ area/
COPY player/ player/
COPY doc/ doc/
COPY README* CHANGELOG.quickmud ./
ENV PYTHONPATH=/opt/charm/game PYTHONDONTWRITEBYTECODE=1
RUN python3 -m compileall -q game/charm \
 && mkdir -p log gods notes \
 && chmod +x area/startup.sh \
 && chown -R charm:charm /opt/charm
USER charm
WORKDIR /opt/charm/area
EXPOSE 4000
ENTRYPOINT ["./startup.sh"]
CMD ["4000"]
