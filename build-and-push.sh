#!/bin/sh
# Build & push Docker image with config.env baked in.
# Usage: ./build-and-push.sh [tag]
#   tag defaults to "iroennys-admin/compresor-bot:latest"

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/compresor_data/config.env"
TAG="${1:-iroennys-admin/compresor-bot:latest}"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ No se encuentra compresor_data/config.env"
    exit 1
fi

# Build args from config.env (skip comments and blank lines)
BUILD_ARGS=""
while IFS='=' read -r key val || [ -n "$key" ]; do
    case "$key" in
        ''|'#'*) continue ;;
    esac
    BUILD_ARGS="$BUILD_ARGS --build-arg ${key}=${val}"
done < "$ENV_FILE"

echo "🔨 Building $TAG ..."
# shellcheck disable=SC2086
docker build $BUILD_ARGS -t "$TAG" "$SCRIPT_DIR"

echo "📦 Pushing $TAG ..."
docker push "$TAG"

echo "✅ Done: $TAG"
