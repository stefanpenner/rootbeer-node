// Regenerates trust/mozilla-no-emsign.pem and tests/fixtures/emsign-roots.pem.
// Usage: node make_bundles.js <cacert.pem> <out-no-emsign.pem> <out-emsign.pem>
// Run this with a stock Node 20. Stock 20 still bundles all four emSign roots.
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const tls = require('tls');

const [input, outNoEmsign, outEmsign] = process.argv.slice(2);
const isEmsign = (pem) => /emsign|emudhra/i.test(new crypto.X509Certificate(pem).subject);
const blocks = fs.readFileSync(input, 'latin1').match(
    /-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----/g);

const kept = blocks.filter((pem) => !isEmsign(pem));
const emsign = tls.rootCertificates.filter(isEmsign);
fs.writeFileSync(outNoEmsign, kept.join('\n') + '\n');
fs.writeFileSync(outEmsign, emsign.join('\n') + '\n');
console.log(`kept ${kept.length} of ${blocks.length}, dropped ${blocks.length - kept.length}`);
for (const pem of emsign) console.log(new crypto.X509Certificate(pem).subject.replace(/\n/g, ', '));
