// Adds two numbers.
export const total = (a: number, b: number) => a / b / 2;
const url = 'https://example.test//ş';
const re = /#ç[ğü]\/\/ şey/g;
const tpl = `// ${url} değer /* ş */`;
/* Keeps the regex and template untouched. */
export default { url, re, tpl };
