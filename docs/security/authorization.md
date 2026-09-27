# WAFlow AI Authorization & Tenant Isolation

**Document Type:** Security Architecture
**Project:** WAFlow AI
**Milestone:** 4C — Authorization & Tenant Isolation Foundation
**Status:** Implemented
**Last Updated:** September 2026

---

## 1. Overview

WAFlow AI is a multi-tenant SaaS platform where a single application instance serves multiple businesses.

Because multiple businesses share the same application and database infrastructure, authorization and tenant isolation are security-critical requirements.

The authorization system establishes:

1. The authenticated user.
2. The user's active membership in a tenant.
3. The user's tenant authorization context.
4. The user's role within that tenant.
5. The permissions granted to that role.
6. The tenant scope under which database operations may occur.

The fundamental security principle is:

> **The client may request a tenant, but the server must determine whether the authenticated user is actually authorized to access that tenant.**

A frontend-provided `tenant_id` is therefore treated only as a selector. It is never treated as proof of authorization.

---

# 2. Security Objectives

The authorization layer is designed to provide the following guarantees:

* Users must authenticate before accessing protected resources.
* Invalid or expired access tokens must be rejected.
* Suspended or deleted users must not access protected resources.
* Users may access only tenants for which they have an active membership.
* Suspended tenants must not be accessible.
* Suspended memberships must not be usable.
* Tenant identity must be established server-side.
* Roles must be resolved from the authenticated user's membership.
* Permissions must be resolved from the database.
* Authorization failures must return HTTP `403 Forbidden`.
* Authentication failures must return HTTP `401 Unauthorized`.
* Tenant-scoped operations must use the validated tenant context.
* Frontend claims must never be trusted as authorization evidence.

---

# 3. Authentication vs Authorization

Authentication and authorization are separate security responsibilities.

## 3.1 Authentication

Authentication answers:

> **Who is making this request?**

WAFlow AI uses a JWT access token to identify the authenticated user.

The access token identifies the user but does not establish tenant authorization.

The authentication dependency is:

```text
get_current_user()
```

Its responsibility is to:

1. Extract the bearer token.
2. Validate the JWT.
3. Verify the token type.
4. Resolve the user.
5. Verify that the user is active.

Authentication failures produce `401 Unauthorized`.

---

## 3.2 Authorization

Authorization answers:

> **What is this authenticated user allowed to do?**

WAFlow AI performs authorization using:

```text
User
  ↓
Membership
  ↓
Tenant
  ↓
Role
  ↓
Permission
```

The authorization layer therefore does not rely only on the JWT.

The database remains the authoritative source for:

* Tenant membership
* Membership status
* Tenant status
* Role
* Role permissions

---

# 4. Authorization Flow

The authorization flow is:

```text
HTTP Request
      │
      ▼
Bearer Access Token
      │
      ▼
get_current_user()
      │
      ▼
Authenticated User
      │
      ▼
require_tenant_membership()
      │
      ├── Membership exists?
      │
      ├── Membership ACTIVE?
      │
      └── Tenant ACTIVE?
      │
      ▼
TenantContext
      │
      ├── User ID
      ├── Tenant ID
      ├── Membership ID
      ├── Role ID
      └── Role Name
      │
      ├───────────────┐
      ▼               ▼
require_role()   require_permission()
      │               │
      ▼               ▼
   Role Check     Permission Check
      │               │
      └───────┬───────┘
              ▼
       Authorized Request
```

Every layer builds on the previous security boundary.

---

# 5. Tenant Isolation Model

WAFlow AI uses a shared PostgreSQL database with tenant-aware application authorization.

The primary tenant-isolation model is:

```text
Tenant
   │
   ├── Membership
   │       │
   │       └── User
   │
   └── Tenant-owned resources
```

A user does not automatically have access to every tenant in the database.

A user must have an active membership connecting them to the requested tenant.

---

# 6. Tenant ID Is Not an Authorization Credential

A client may send:

```text
tenant_id
```

as part of a request.

For example:

```http
GET /api/v1/customers?tenant_id=<tenant-id>
```

However, the server must never assume that the client is authorized simply because it supplied a valid UUID.

The server performs an authorization query equivalent to:

```text
Find Membership
WHERE
    membership.user_id = authenticated_user.id
AND
    membership.tenant_id = requested_tenant_id
AND
    membership.status = ACTIVE
```

The tenant must also satisfy:

```text
tenant.status = ACTIVE
```

Only after these checks succeed can the request proceed.

---

# 7. Why Tenant Identity Is Resolved Server-Side

A malicious client could attempt to change:

```text
tenant_id=A
```

to:

```text
tenant_id=B
```

in order to access another business.

The application must therefore never use frontend state such as:

```javascript
currentUser.tenantId
```

as proof of access.

Instead:

```text
Frontend tenant_id
        │
        ▼
Request selector
        │
        ▼
Database membership lookup
        │
        ├── Authorized → Continue
        │
        └── Unauthorized → 403
```

This prevents tenant access from being determined by client-controlled data.

---

# 8. TenantContext

Once authentication and tenant membership have been validated, WAFlow AI creates an immutable `TenantContext`.

The context contains:

```python
TenantContext(
    user_id,
    tenant_id,
    membership_id,
    role_id,
    role_name,
)
```

The context is implemented as a frozen dataclass.

Conceptually:

```text
TenantContext
├── user_id
├── tenant_id
├── membership_id
├── role_id
└── role_name
```

These values originate from the authenticated user and validated database membership.

They do not originate from untrusted frontend claims.

---

# 9. Immutable Authorization Context

`TenantContext` is defined as immutable.

The implementation uses:

```python
@dataclass(frozen=True, slots=True)
class TenantContext:
    ...
```

The purpose is to prevent application code from accidentally modifying the authorization context during request processing.

Once the server establishes:

```text
User A
Tenant B
Membership C
Role AGENT
```

downstream application code should not be able to mutate that context into:

```text
User A
Tenant X
Role OWNER
```

The authorization context therefore represents a trusted request boundary.

---

# 10. Membership Validation

The dependency:

```text
require_tenant_membership()
```

is responsible for validating tenant access.

The validation requires:

### 10.1 Authenticated User

The JWT must identify a valid user.

### 10.2 Active Membership

The user must have:

```text
MembershipStatus.ACTIVE
```

for the requested tenant.

### 10.3 Active Tenant

The tenant must have:

```text
TenantStatus.ACTIVE
```

If any of these requirements fail, authorization is denied.

---

# 11. Suspended Membership

A user may exist and have a valid access token while their membership in a particular tenant has been suspended.

For example:

```text
User
 ├── Tenant A → ACTIVE membership
 └── Tenant B → SUSPENDED membership
```

The user may continue to access Tenant A but must not access Tenant B.

This is an important property of the multi-tenant model.

Authorization is therefore evaluated at the membership level rather than assuming that user authentication grants universal tenant access.

---

# 12. Suspended Tenant

A tenant may also be suspended.

For example:

```text
Tenant
 └── status = SUSPENDED
```

Even if a user has an active membership in that tenant, access must be rejected.

The authorization rule is:

```text
User active
+
Membership active
+
Tenant active
=
Authorized tenant context
```

If the tenant is not active, the request is rejected.

---

# 13. Roles

WAFlow AI currently defines five tenant roles:

| Role      | Purpose                                    |
| --------- | ------------------------------------------ |
| `OWNER`   | Full access to the tenant                  |
| `ADMIN`   | Administrative access                      |
| `MANAGER` | Management access to operational resources |
| `AGENT`   | Customer support and conversation access   |
| `VIEWER`  | Read-only access to permitted resources    |

Roles are associated with memberships.

Conceptually:

```text
Membership
    │
    └── Role
          │
          └── RolePermissions
```

A user can therefore have different roles in different tenants.

For example:

```text
User A
 ├── Tenant A → OWNER
 └── Tenant B → AGENT
```

Authorization must use the role belonging to the membership for the currently requested tenant.

---

# 14. Role-Based Authorization

Role authorization is provided through:

```text
require_role(...)
```

For example:

```python
OwnerContext = Annotated[
    TenantContext,
    Depends(require_role("OWNER")),
]
```

An endpoint can then require the owner role.

The authorization flow becomes:

```text
Request
  ↓
Authenticated User
  ↓
Active Tenant Membership
  ↓
TenantContext
  ↓
Role = OWNER?
  ↓
Continue / 403
```

Multiple roles may also be accepted.

For example:

```python
Depends(require_role("OWNER", "ADMIN"))
```

This allows either role to access the endpoint.

---

# 15. Permission-Based Authorization

Roles provide broad authorization categories.

Permissions provide more granular control.

WAFlow AI uses the established:

```text
resource.action
```

permission naming convention.

Examples:

```text
customers.read
customers.create
customers.update
customers.delete

conversations.read
conversations.reply
conversations.resolve

billing.read
billing.manage
billing.change_plan

knowledge.read
knowledge.upload
knowledge.process
```

The permission is resolved from the role's database relationships.

---

# 16. Permission Resolution

The permission authorization process is:

```text
TenantContext
      │
      ▼
Role ID
      │
      ▼
RolePermission
      │
      ▼
Permission
      │
      ▼
Permission Name
      │
      ▼
Authorized / 403
```

The system does not rely on frontend permissions.

For example, the frontend may hide a button when the user lacks:

```text
billing.change_plan
```

but hiding the button is not a security control.

The backend must independently verify:

```text
billing.change_plan
```

before executing the operation.

---

# 17. Frontend Authorization Is Not Security

Frontend authorization is useful for user experience.

For example:

```text
AGENT
 └── Hide billing administration controls
```

However, frontend restrictions can be bypassed.

A malicious user could manually send:

```http
POST /api/v1/billing/change-plan
```

Therefore every protected backend endpoint must enforce authorization server-side.

The rule is:

> **Frontend authorization controls visibility. Backend authorization controls access.**

---

# 18. HTTP 401 vs 403

WAFlow AI distinguishes authentication failures from authorization failures.

## 18.1 HTTP 401 Unauthorized

Use `401 Unauthorized` when the request cannot be authenticated.

Examples:

* No access token
* Invalid access token
* Expired access token
* Invalid token type
* User referenced by the token does not exist

Conceptually:

```text
Who are you?
      ↓
Cannot establish identity
      ↓
401
```

---

## 18.2 HTTP 403 Forbidden

Use `403 Forbidden` when the user is authenticated but is not allowed to perform the requested operation.

Examples:

* Suspended user
* Missing tenant membership
* Suspended membership
* Suspended tenant
* Insufficient role
* Missing permission

Conceptually:

```text
Who are you?
      ↓
Authenticated
      ↓
Are you allowed?
      ↓
No
      ↓
403
```

This distinction makes authorization failures easier to reason about and test.

---

# 19. Protected Endpoint Pattern

A tenant-scoped endpoint should use the authorization dependencies rather than implementing authorization manually in every route.

Conceptually:

```python
CustomersReadContext = Annotated[
    TenantContext,
    Depends(require_permission("customers.read")),
]
```

An endpoint can then receive the validated context:

```python
async def list_customers(
    tenant_context: CustomersReadContext,
):
    ...
```

The endpoint receives a trusted:

```text
TenantContext
```

instead of trusting a frontend-provided tenant identity.

---

# 20. Tenant-Scoped Database Queries

Authorization alone is not sufficient.

After obtaining the tenant context, database queries must also be tenant-scoped.

For example, a customer query should conceptually follow:

```python
select(Customer).where(
    Customer.tenant_id == tenant_context.tenant_id,
)
```

The critical rule is:

> **Every tenant-owned resource query must include the authorized tenant scope.**

Do not use:

```python
select(Customer)
```

for a tenant-owned operation unless there is a deliberate system-level reason.

Prefer:

```python
select(Customer).where(
    Customer.tenant_id == tenant_context.tenant_id,
)
```

---

# 21. Defense Against Cross-Tenant Data Access

A secure request should follow:

```text
JWT
 │
 ▼
User
 │
 ▼
Membership
 │
 ▼
TenantContext
 │
 ▼
Tenant-scoped Query
 │
 ▼
Tenant-owned Data
```

The system must not allow:

```text
JWT
 │
 ▼
User
 │
 ▼
Frontend tenant_id
 │
 ▼
Unrestricted Query
 │
 ▼
Potential cross-tenant data
```

The second pattern is prohibited.

---

# 22. Example Cross-Tenant Attack

Assume:

```text
Tenant A = Business A
Tenant B = Business B
```

A user belongs to Tenant A.

The user sends:

```http
GET /api/v1/customers?tenant_id=<tenant-b-id>
```

The server evaluates:

```text
Authenticated User
       │
       ▼
Membership for Tenant B?
       │
       ├── NO
       │
       ▼
403 Forbidden
```

The request must not proceed to the customer query.

This authorization check must happen before accessing Tenant B's data.

---

# 23. Role vs Permission

Role and permission authorization serve different purposes.

### Role

Answers:

> What organizational role does this user have?

Examples:

```text
OWNER
ADMIN
MANAGER
AGENT
VIEWER
```

### Permission

Answers:

> Is this role allowed to perform this specific operation?

Examples:

```text
customers.read
customers.update
billing.change_plan
```

Permission-based authorization should generally be preferred for granular application operations because it avoids coupling business endpoints too tightly to organizational role names.

---

# 24. Authorization Dependency Responsibilities

The current authorization dependency layer contains several responsibilities.

### `get_current_user()`

Establishes the authenticated user.

### `require_tenant_membership()`

Establishes:

* User membership
* Membership status
* Tenant status

### `get_tenant_context()`

Builds the immutable authorization context.

### `require_role()`

Enforces role-based access.

### `_has_permission()`

Checks the database role-permission relationship.

### `require_permission()`

Enforces permission-based access.

Together these form the authorization foundation for tenant-scoped application modules.

---

# 25. Security Rules

The following rules are mandatory for future development.

## Rule 1 — Never trust tenant IDs from the frontend

A tenant ID identifies the requested scope.

It does not establish authorization.

---

## Rule 2 — Never trust frontend roles

Do not accept:

```json
{
  "role": "OWNER"
}
```

as authorization evidence.

Roles must come from the authenticated user's database membership.

---

## Rule 3 — Never trust frontend permissions

The backend must resolve permissions independently.

---

## Rule 4 — Every tenant-owned resource must be tenant-scoped

Queries must use:

```text
authorized tenant context
```

as their tenant boundary.

---

## Rule 5 — Authorization must occur before sensitive operations

Do not perform the database operation first and authorize afterward.

Correct:

```text
Authenticate
→ Authorize
→ Query
→ Mutate
```

Incorrect:

```text
Query
→ Mutate
→ Check authorization
```

---

## Rule 6 — Do not place tenant authorization solely in the frontend

The frontend is not a security boundary.

---

## Rule 7 — Do not put mutable authorization state in the JWT

The JWT identifies the user.

Tenant membership and permissions remain database-authoritative.

This allows changes such as:

```text
User becomes suspended
Membership becomes suspended
Role changes
Permission changes
Tenant becomes suspended
```

to take effect without relying on stale authorization claims.

---

# 26. Testing Requirements

Authorization behavior must be covered by automated tests.

The Milestone 4C test suite verifies:

1. Missing authentication returns `401`.
2. Invalid authentication returns `401`.
3. Active tenant membership is authorized.
4. A user cannot access another tenant.
5. Suspended membership is rejected.
6. Suspended tenant is rejected.
7. An owner can access owner-protected functionality.
8. An agent cannot access owner-only functionality.
9. An agent can use an allowed permission.
10. An agent cannot use a restricted permission.
11. An owner can use the required billing permission.

The authorization test suite currently contains:

```text
11 tests
11 passed
```

The complete backend test suite currently contains:

```text
23 tests
23 passed
```

---

# 27. Current RBAC Permission Model

WAFlow AI currently uses permissions following the:

```text
resource.action
```

format.

Examples include:

```text
ai.manage
ai.read
ai.test

analytics.export
analytics.read

api_keys.create
api_keys.read
api_keys.revoke

appointments.cancel
appointments.create
appointments.read
appointments.update

audit.read

billing.change_plan
billing.manage
billing.read

conversations.assign
conversations.read
conversations.reply
conversations.resolve
conversations.takeover

customers.assign
customers.create
customers.delete
customers.read
customers.update

knowledge.delete
knowledge.process
knowledge.read
knowledge.update
knowledge.upload

settings.read
settings.update

team.change_role
team.invite
team.read
team.remove
team.update

whatsapp.manage
whatsapp.read
whatsapp.send

workflows.activate
workflows.create
workflows.delete
workflows.read
workflows.update
```

These permissions are assigned to roles through the `RolePermission` relationship.

---

# 28. Multi-Tenant Authorization Example

Consider a user with:

```text
User: Alice
```

Memberships:

```text
Tenant A
Role: OWNER

Tenant B
Role: AGENT
```

When Alice accesses Tenant A:

```text
Tenant A
Role = OWNER
```

An owner-only operation may succeed.

When Alice accesses Tenant B:

```text
Tenant B
Role = AGENT
```

The same owner-only operation must fail.

This demonstrates why the application cannot simply store one global role for a user.

The role belongs to the user's membership in a particular tenant.

---

# 29. Future PostgreSQL Row-Level Security

Application-level authorization is the primary mechanism currently implemented.

PostgreSQL Row-Level Security (RLS) may later be introduced as an additional defense-in-depth mechanism.

The potential architecture would become:

```text
Application Authorization
          +
PostgreSQL Row-Level Security
          =
Defense in Depth
```

RLS should not be treated as a replacement for clear application authorization logic.

Before introducing RLS, the database session and transaction model must be designed carefully so tenant context cannot be accidentally shared across requests.

---

# 30. Future Authorization Improvements

Potential future improvements include:

* PostgreSQL Row-Level Security
* Permission caching
* Fine-grained resource authorization
* API-key-specific permission scopes
* Service-to-service authorization
* Organization-level system administrators
* Audit logging for authorization failures
* Security event monitoring
* Rate limiting on protected endpoints
* Automated tenant-isolation penetration tests
* Authorization policy testing across all tenant-owned resources

These are future enhancements and are not required to consider the current Milestone 4C foundation operational.

---

# 31. Developer Checklist

Before creating a new tenant-scoped endpoint, verify:

* [ ] Authentication dependency is applied.
* [ ] Tenant membership is validated.
* [ ] Tenant context is obtained from the server.
* [ ] Required role or permission is enforced.
* [ ] Tenant-owned queries filter by `tenant_context.tenant_id`.
* [ ] User-controlled tenant IDs are not trusted directly.
* [ ] Frontend role claims are not trusted.
* [ ] Frontend permissions are not trusted.
* [ ] Unauthorized access returns `403`.
* [ ] Missing/invalid authentication returns `401`.
* [ ] Cross-tenant access is covered by tests.
* [ ] Suspended membership behavior is tested.
* [ ] Suspended tenant behavior is tested.
* [ ] Authorization changes are audited where appropriate.

---

# 32. Security Review Summary

Milestone 4C establishes the authorization and tenant-isolation foundation for WAFlow AI.

The security boundary is:

```text
Authenticated User
        ↓
Active Membership
        ↓
Active Tenant
        ↓
TenantContext
        ↓
Role / Permission
        ↓
Tenant-Scoped Operation
```

The central design principle is:

> **Authentication identifies the user; database-backed membership establishes tenant access; roles and permissions determine what the user may do; tenant-scoped queries determine what data the operation may touch.**

This separation provides the foundation required for the next application modules to implement secure tenant-scoped functionality consistently.

---

## 33. Milestone 4C Verification

Milestone 4C is considered verified when all of the following pass:

```bash
pytest -q
ruff check app tests
python -m compileall app
git diff --check
alembic current
alembic heads
```

Current verified state:

```text
Backend tests:        23 passed
Ruff:                 All checks passed
Python compilation:   Passed
Git diff check:       Passed
Alembic current:      4a7c9d2e1f30
Alembic head:         4a7c9d2e1f30
```

No database migration is required for the authorization dependency layer introduced in Milestone 4C.
