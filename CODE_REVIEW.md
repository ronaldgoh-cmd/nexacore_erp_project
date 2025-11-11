# Code Review

## Critical Issues

### Hard-coded superadministrator backdoor credentials
The application ships with a built-in `superadministrator` account that always authenticates with the public password `superadministrator123!`. Both the login loop and the authentication helpers treat this credential pair as a bypass, even creating the database row on demand when it is used.【F:nexacore_erp/app.py†L14-L121】【F:nexacore_erp/core/auth.py†L19-L63】 This means anyone with access to the client can obtain unrestricted superadmin access, defeating all other security controls. Remove the hard-coded password flow and require administrators to provision secure accounts during deployment.

### Passwords cached locally in plain text
The login dialog offers a "Remember password on this PC" option that stores the raw password string in `QSettings` under the current user profile. There is no encryption or OS credential locker integration, so an attacker with filesystem access can recover user secrets directly from the configuration store.【F:nexacore_erp/ui/login_dialog.py†L36-L100】 Prefer delegating to the operating system's secure credential storage or drop the option entirely.

### Recoverable plaintext copies of user passwords
The account management UI persists a decryptable copy of every user's password (`password_enc`) so the table can reveal it on demand. The encryption key is generated on first run and stored unprotected in `~/.nexacore_erp/secret.key`; if the optional cryptography dependency is missing, the code falls back to reversible Base64 encoding. Password hashes also fall back to storing the raw password when hashing fails. Combined with the superadmin helper, this guarantees that the database (or local key file) leaks reusable plaintext credentials.【F:nexacore_erp/modules/account_management/ui/users_tab.py†L18-L379】【F:nexacore_erp/app.py†L30-L45】 Remove the password viewer, stop storing reversible password data, and ensure hashing failures are treated as errors, not silent degradations.

## Additional Observations

* The password hashing helper is optional throughout the code (`_hash` defaults to `None`), causing account creation and resets to store raw passwords when the dependency is missing. This silent downgrade is dangerous and should be treated as a fatal error instead of an implicit fallback.【F:nexacore_erp/modules/account_management/ui/users_tab.py†L18-L379】
* The login bypass creates or updates the superadmin row with `is_active=True` and will overwrite any disabled state, preventing administrators from locking out the account.【F:nexacore_erp/app.py†L26-L79】
