const a = '/* ş */'; /* temporary value */
const b = a.replace(/\/\/ğ/, ''); // strips the marker
module.exports = b;
