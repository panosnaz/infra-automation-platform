FROM python:3.12-slim

WORKDIR /app

# Terraform CLI — Milestone 6A (Real Terraform Integration). Pinned to the
# exact version already proven against platform/terraform/aci/'s existing
# state (Phase 3), installed via the official release archive rather than
# adding HashiCorp's apt repo/GPG key for a single binary.
ARG TERRAFORM_VERSION=1.14.9
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && curl -fsSL -o /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && unzip /tmp/terraform.zip -d /usr/local/bin \
    && rm /tmp/terraform.zip \
    && apt-get purge -y --auto-remove unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --from=canonical_intent_src . ./canonical_intent
COPY --from=generator_src . ./generator_src

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=2).raise_for_status()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
