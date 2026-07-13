import { createHash, createHmac } from "node:crypto";

export function safeIdentityFingerprint(value: string): string {
  return createHash("sha256").update(value).digest("hex").slice(0, 12);
}

function base64url(value: string): string {
  return Buffer.from(value).toString("base64url");
}

export function signOnboardingAssertion({
  subject, transaction, secret, issuer, audience, issuedAt, nonce,
}: {
  subject: string;
  transaction: string;
  secret: string;
  issuer: string;
  audience: string;
  issuedAt: number;
  nonce: string;
}): string {
  const normalizedSubject = subject.trim();
  if (!normalizedSubject) throw new Error("Auth0 subject is required.");
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = base64url(JSON.stringify({
    sub: normalizedSubject,
    iss: issuer,
    aud: audience,
    iat: issuedAt,
    exp: issuedAt + 60,
    jti: nonce,
    tx_hash: createHash("sha256").update(transaction).digest("hex"),
    typ: "onboarding",
  }));
  const signature = createHmac("sha256", secret)
    .update(`${header}.${payload}`)
    .digest("base64url");
  return `${header}.${payload}.${signature}`;
}
