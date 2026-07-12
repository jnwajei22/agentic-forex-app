import { Auth0Client } from "@auth0/nextjs-auth0/server";

const issuer = process.env.AUTH0_ISSUER_BASE_URL;
const domain = issuer?.replace(/^https?:\/\//, "").replace(/\/$/, "");

export const auth0 = new Auth0Client({
  domain,
  clientId: process.env.AUTH0_CLIENT_ID,
  clientSecret: process.env.AUTH0_CLIENT_SECRET,
  secret: process.env.AUTH0_SECRET,
  appBaseUrl: process.env.AUTH0_BASE_URL,
  signInReturnToPath: "/dashboard",
  authorizationParameters: {
    audience: process.env.AUTH0_AUDIENCE,
    scope: "openid profile email forex:read forex:preview",
  },
});
