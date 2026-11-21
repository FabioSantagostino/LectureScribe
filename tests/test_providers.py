import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scribelane_credentials import Vault
from scribelane_providers import categorize, stitch, ProviderError, transcribe_long

class FakeKeyring:
    def __init__(self): self.store={}
    def set_password(self, s, k, v): self.store[(s,k)]=v
    def get_password(self, s, k): return self.store.get((s,k))
    def delete_password(self, s, k): self.store.pop((s,k),None)

class Services(unittest.TestCase):
    def test_provider_error(self):
        self.assertEqual(categorize(401).category,'authentication')
        self.assertEqual(categorize(429,'30').retry_after,30)
        self.assertEqual(categorize(503).category,'temporary')

    def test_stitch(self):
        self.assertEqual(stitch('hello this is a test', 'is a test on audio'), 'on audio')

    def test_vault_roundtrip_no_plaintext(self):
        with tempfile.TemporaryDirectory() as td:
            stub=FakeKeyring()
            with patch.object(Vault,'_keyring',return_value=stub):
                v=Vault(Path(td)/'vault.json')
                item=v.add('groq','Personal','SUPERSECRET')
                self.assertNotIn('SUPERSECRET',(Path(td)/'vault.json').read_text())
                v2=Vault(Path(td)/'vault.json')
                self.assertEqual(v2.get_secret(item['id']),'SUPERSECRET')
                v2.edit(item['id'],name='Renamed',enabled=False)
                self.assertFalse(v2.items[0]['enabled'])
                v2.delete(item['id'])
                self.assertIsNone(v2.get_secret(item['id']))

    def test_chunk_resume_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            media=Path(td)/'audio.mp4';media.write_bytes(b'fake-media')
            output=Path(td)/'out';output.mkdir()
            count={'n':0}
            def mock_chunks(*args,**kwargs):
                for i in range(3):yield i,3,i*10,i*10+11,media
            def mock_transcribe(*args,**kwargs):
                count['n']+=1
                return 'text'
            with patch('scribelane_providers.chunks',side_effect=mock_chunks), patch('scribelane_providers.transcribe_chunk',side_effect=mock_transcribe):
                args=dict(provider='groq',model='whisper-large-v3-turbo',secret='secret',output_dir=output,job_id='test',key_id='one')
                self.assertEqual(len(transcribe_long(media,**args)),3)
                self.assertEqual(len(transcribe_long(media,**args)),3)
                self.assertEqual(transcribe_long(media, **args, timed=True),
                                 [(0, 10, 'text'), (10, 20, 'text'), (20, 31, 'text')])
                self.assertEqual(count['n'],3)
                transcribe_long(media,**{**args,'key_id':'two'})
                self.assertEqual(count['n'],6)

if __name__=='__main__':unittest.main()
