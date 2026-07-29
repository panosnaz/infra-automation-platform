FROM python:3.12-slim

WORKDIR /app

# mcp-server/ (top-level, per Platform-v2-Reference-Architecture.md §9's
# repository structure) is the build context -- this Dockerfile lives in
# docker/mcp-server/ alongside the compose file, matching every other
# service in docker/other-containers/.
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# MCP over stdio has no long-running network listener to heathcheck the
# usual way; docker-compose.yml's healthcheck instead runs a one-shot
# "does the package import and build a server" check.
ENTRYPOINT ["python3", "-m", "mcp_server.main"]
