export function engineFixture(settings, engine) {
  const prefix = 'E2E_' + engine.toUpperCase() + '_';
  const values = Object.fromEntries(Object.entries(settings)
    .filter(([key]) => key.startsWith(prefix))
    .map(([key, value]) => ['E2E_' + key.slice(prefix.length), value]));
  if (!Object.keys(values).length) throw new Error('Missing fixture for ' + engine);
  return values;
}

export async function browserRunStatuses(runs, reportFailure) {
  return (await Promise.allSettled(runs)).map((result) => {
    if (result.status === 'fulfilled') return result.value;
    reportFailure(result.reason);
    return 1;
  });
}
