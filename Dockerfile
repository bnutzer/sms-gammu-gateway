FROM python:3-alpine AS gammu-builder

ARG GAMMU_VERSION=1.43.2
ARG GAMMU_SHA256=bd521c0483a52808abf885cf0dd9f42036354a5f94518ffe064cb9e7ef23fd02

RUN apk add --no-cache \
	build-base cmake samurai linux-headers \
	bluez-dev curl-dev gettext-dev libusb-dev

ADD https://github.com/gammu/gammu/releases/download/${GAMMU_VERSION}/Gammu-${GAMMU_VERSION}.tar.gz /src/gammu.tar.gz
RUN echo "${GAMMU_SHA256}  /src/gammu.tar.gz" | sha256sum -c -

WORKDIR /src
RUN tar xzf gammu.tar.gz && mv Gammu-${GAMMU_VERSION} gammu

WORKDIR /src/gammu
RUN cmake -G Ninja -B build \
		-DCMAKE_BUILD_TYPE=None \
		-DBUILD_SHARED_LIBS=ON \
		-DCMAKE_INSTALL_PREFIX=/usr \
		-DWITH_NOKIA_SUPPORT=ON \
		-DWITH_BLUETOOTH=ON \
		-DWITH_IRDA=ON \
		-DLIBINTL_LIBRARIES=intl \
	&& cmake --build build \
	&& cmake --install build --prefix=/gammu-install

# Base stage: runtime libraries needed by libGammu, no build tooling
FROM python:3-alpine AS base

RUN apk add --no-cache pkgconfig bluez-libs libusb gettext curl

COPY --from=gammu-builder /gammu-install/bin/ /usr/bin/
COPY --from=gammu-builder /gammu-install/lib/ /usr/lib/
COPY --from=gammu-builder /gammu-install/include/ /usr/include/

RUN python -m pip install --no-cache-dir -U pip

FROM base AS final
COPY requirements.txt .
# python-gammu's C source trips a GCC 14+ hard error (return-with-value in a
# void function in gammu.c); upstream bug, not fixed as of 3.2.6.
ENV CFLAGS="-Wno-error=return-mismatch"
RUN apk add --no-cache --virtual .build-deps libffi-dev openssl-dev gcc musl-dev python3-dev cargo \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

ENV BASE_PATH=/sms-gw
RUN mkdir $BASE_PATH /ssl
WORKDIR $BASE_PATH
COPY . $BASE_PATH

ENTRYPOINT [ "./docker_init.sh" ]
