"""Credential metadata in JSON, API secrets only in OS credential store."""
import json
import uuid
from pathlib import Path

SERVICE = 'ScribeLane/API'

class Vault:
    def __init__(self, path):
        self.path = Path(path)
        try:
            items = json.loads(self.path.read_text(encoding='utf8'))
            self.items = items if isinstance(items,list) else []
        except (OSError, ValueError):
            self.items = []

    def _keyring(self):
        import keyring
        import os
        if os.name == "nt":
            # Force the protected Windows vault, never fall back to plaintext backends.
            from keyring.backends.Windows import WinVaultKeyring
            if not isinstance(keyring.get_keyring(), WinVaultKeyring):
                keyring.set_keyring(WinVaultKeyring())
        return keyring

    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.items,indent=2,ensure_ascii=False),encoding='utf8')
        temporary.replace(self.path)

    def add(self, provider, name, secret):
        if provider not in ('groq','gemini','openai') or not secret.strip():
            raise ValueError('Invalid provider or secret')
        identifier = str(uuid.uuid4())
        self._keyring().set_password(SERVICE, identifier, secret.strip())
        item = {'id':identifier,'provider':provider,'name':name.strip() or provider,
                'enabled':True}
        self.items.append(item)
        self._save()
        return item

    def get_secret(self, identifier):
        if not any(x['id']==identifier for x in self.items):
            return None
        try:
            return self._keyring().get_password(SERVICE,identifier)
        except Exception:
            return None

    def edit(self, identifier, *, name=None, enabled=None, secret=None):
        item = next(x for x in self.items if x['id']==identifier)
        if secret is not None:
            self._keyring().set_password(SERVICE,identifier,secret)
        if name is not None:
            item['name']=name.strip()
        if enabled is not None:
            item['enabled']=bool(enabled)
        self._save()

    def delete(self, identifier):
        try:
            self._keyring().delete_password(SERVICE,identifier)
        except Exception:
            pass
        self.items=[x for x in self.items if x['id']!=identifier]
        self._save()
