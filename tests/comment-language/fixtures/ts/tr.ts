export const total = (a: number, b: number) => a + b;

/**
 * Toplamı hesaplar.
 */
export function sum(values: number[]) {
  return values.reduce(total, 0); // değerleri toplar
}
