FROM golang:1.25 AS builder

WORKDIR /src

COPY opsnexus-common/go.mod ./opsnexus-common/go.mod
COPY opsnexus-backend/go.mod ./opsnexus-backend/go.mod
COPY opsnexus-backend/go.sum ./opsnexus-backend/go.sum

WORKDIR /src/opsnexus-backend
RUN go mod download

WORKDIR /src
COPY opsnexus-common ./opsnexus-common
COPY opsnexus-backend ./opsnexus-backend

WORKDIR /src/opsnexus-backend
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -o /out/opsnexus-backend ./cmd/server

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /out/opsnexus-backend /usr/local/bin/opsnexus-backend

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/opsnexus-backend"]
