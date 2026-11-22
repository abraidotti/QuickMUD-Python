# The C game's image, kept as the live checks' oracle until cut-over removes src/ (#112, decision 3). Build it from
# the repo root:
#   docker build -f tools/oracle/Dockerfile.c -t charm:c .                       # the runtime image
#   docker build -f tools/oracle/Dockerfile.c --target build -t charm:build .    # the build stage, for port checks
# CC picks the compiler: docker build -f tools/oracle/Dockerfile.c --build-arg CC=clang -t charm:clang .
# The repo root's Dockerfile builds the Python game.

# Build stage: compile the game into area/rom.
FROM ubuntu:26.04 AS build
ARG CC=gcc
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc make libc6-dev libcrypt-dev \
      $( [ "$CC" = clang ] && echo clang ) \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/charm
COPY src/ src/
COPY area/ area/
RUN cd src && make -j"$(nproc)" CC="$CC"

# Runtime stage: the binary, areas and data dirs, plus the README, credits and
# licence files every copy must keep (see README.md, Licence terms).
FROM ubuntu:26.04
RUN apt-get update \
 && apt-get install -y --no-install-recommends libcrypt1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --no-create-home --home-dir /opt/charm charm
WORKDIR /opt/charm
COPY --from=build /opt/charm/area/ area/
COPY player/ player/
COPY doc/ doc/
COPY README* CHANGELOG.quickmud ./
RUN mkdir -p log gods notes \
 && chmod +x area/startup.sh area/rom \
 && chown -R charm:charm /opt/charm
USER charm
WORKDIR /opt/charm/area
EXPOSE 4000
ENTRYPOINT ["./startup.sh"]
CMD ["4000"]
