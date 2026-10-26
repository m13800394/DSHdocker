import { networkInterfaces } from 'node:os';

export function containerAddress() {
  const addresses = Object.values(networkInterfaces()).flat().filter(
    address => address && address.family === 'IPv4' && !address.internal,
  );
  if (addresses.length !== 1) {
    throw new Error(`Expected one container IPv4 address, found ${addresses.length}. Use one Compose network.`);
  }
  return addresses[0].address;
}
