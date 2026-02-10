# FROM python:3
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim

WORKDIR /root
# COPY dists repo
# COPY pool repo
COPY main.py main.py
COPY rippled_3.1.0-1_amd64.deb rippled_3.1.0-1_amd64.deb
COPY install_dependencies.sh install_dependencies.sh

RUN ./install_dependencies.sh
CMD [ "python", "-m", "http.server" ]
