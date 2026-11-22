# The game (#112, decision 3). The C game's image is tools/oracle/Dockerfile.c at the c-final tag.
#   docker build -t quickmud .
FROM ubuntu:26.04
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --no-create-home --home-dir /opt/quickmud quickmud
WORKDIR /opt/quickmud
# The game, its areas and data dirs, plus the README, credits and licence files every copy must keep (see
# README.md, Licence terms).
COPY game/quickmud/ game/quickmud/
COPY area/ area/
COPY player/ player/
COPY doc/ doc/
COPY README* CHANGELOG.quickmud ./
ENV PYTHONPATH=/opt/quickmud/game PYTHONDONTWRITEBYTECODE=1
RUN python3 -m compileall -q game/quickmud \
 && mkdir -p log gods notes \
 && chmod +x area/startup.sh \
 && chown -R quickmud:quickmud /opt/quickmud
USER quickmud
WORKDIR /opt/quickmud/area
EXPOSE 4000
ENTRYPOINT ["./startup.sh"]
CMD ["4000"]
