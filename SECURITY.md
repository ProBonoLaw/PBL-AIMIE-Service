# Security

Report vulnerabilities privately through the repository's **Security → Report a
vulnerability** feature when enabled. Do not put credentials, internal resource
identifiers, legal records or personal data into public issues or pull requests.
Provide a minimal synthetic reproduction and the affected revision.

Deployment uses private ingress and external access controls. Several application
routes use anonymous Azure Functions authentication; publishing the source does
not make those routes suitable for an unauthenticated public service. Operators
must configure authentication and account authorization at their service boundary
before exposing a deployment outside its trusted network.

Store credentials in Key Vault or GitHub secrets and private resource identifiers
in private environment configuration. GitHub variables are not automatically
masked in logs. See [deployment configuration](docs/deployment-configuration.md).
