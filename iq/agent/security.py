'''
This module provides a class to sign payloads using a private key.
'''

import base64

from OpenSSL import crypto
from OpenSSL.crypto import PKey

class SecurityProvider:
    '''
    Provides a method to sign a payload using a private key.
    '''

    def __init__(self, access_token: str, client_id: str, client_secret: str):
        # Store the access token.
        self._access_token: str = access_token

        # Store the client ID.
        self._client_id: str = client_id

        # Decode the client secret.
        self._client_secret: bytes = base64.b64decode(client_secret)
        self._client_secret: PKey = crypto.load_privatekey(
            crypto.FILETYPE_PEM, self._client_secret)

    @property
    def access_token(self) -> str:
        '''
        Get the access token.
        '''
        return self._access_token

    @property
    def client_id(self) -> str:
        '''
        Get the client ID.
        '''
        return self._client_id

    def sign(self, payload: bytes) -> str:
        '''
        Create a signature for the payload.
        '''

        # Sign the payload.
        signature: bytes = crypto.sign(
            self._client_secret, payload, 'sha256')

        # Encode the signature in base64 and return it.
        return base64.b64encode(signature).decode('utf-8')
