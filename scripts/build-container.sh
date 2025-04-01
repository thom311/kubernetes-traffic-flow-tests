#!/bin/bash

TAG="${TAG:-quay.io/$USER/kubernetes-traffic-flow-tests:latest}"

set -ex

TAG="${1:-$TAG}"

buildah manifest rm kubernetes-traffic-flow-tests-manifest || true
buildah manifest create kubernetes-traffic-flow-tests-manifest
buildah build --manifest kubernetes-traffic-flow-tests-manifest --platform linux/amd64,linux/arm64 -t "$TAG" .
buildah manifest push --all kubernetes-traffic-flow-tests-manifest "docker://$TAG"
