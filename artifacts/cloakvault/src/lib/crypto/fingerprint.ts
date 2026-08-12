/**
 * BIP32 master fingerprint: first 4 bytes of HASH160(compressed master
 * public key), displayed as XXXX-XXXX uppercase hex.
 */
import { HDKey } from '@scure/bip32';
import { mnemonicToBip39Seed } from './wallet';
import { wipe } from './bytes';

/** Master fingerprint (4 bytes) from a 64-byte BIP39 seed. */
export function masterFingerprintFromSeed(bip39Seed: Uint8Array): Uint8Array {
  const hd = HDKey.fromMasterSeed(bip39Seed);
  const fp = new Uint8Array(4);
  new DataView(fp.buffer).setUint32(0, hd.fingerprint, false);
  hd.wipePrivateData();
  return fp;
}

/** Master fingerprint from a 24-word mnemonic (empty passphrase). */
export function masterFingerprintFromMnemonic(mnemonic: string): Uint8Array {
  const seed = mnemonicToBip39Seed(mnemonic);
  try {
    return masterFingerprintFromSeed(seed);
  } finally {
    wipe(seed);
  }
}

/** Format as XXXX-XXXX uppercase hexadecimal. */
export function formatFingerprint(fp: Uint8Array): string {
  if (fp.length !== 4) throw new Error('Fingerprint must be 4 bytes.');
  const hex = Array.from(fp, (b) => b.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase();
  return `${hex.slice(0, 4)}-${hex.slice(4)}`;
}
