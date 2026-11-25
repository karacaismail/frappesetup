"""Public Python interface for the model gateway."""

from platform_core.model_gateway import gateway, large_file
from platform_core.model_gateway.maintenance import purge_usage_logs as purge_usage_logs


def complete(route, messages, tools=None, schema=None, limit=1024):
	"""Complete a request on a configured route under the current user's permissions."""
	return gateway.complete(route, messages, tools=tools, schema=schema, limit=limit)


def create_file_job(route, file, instruction, limit=1024):
	"""Record a large PDF job and queue its page text step. No provider is called (G-156)."""
	return large_file.create_job(route, file, instruction, limit)


def file_job_status(file_job):
	"""Return the chunk count, cost estimate and chunk states of a large file job."""
	return large_file.job_status(file_job)


def start_file_job(file_job):
	"""Queue every planned chunk after the user has seen the count and the estimate."""
	return large_file.start_job(file_job)


def retry_file_chunk(file_job, chunk_index):
	"""Queue one failed chunk again. Finished chunks are not sent again."""
	return large_file.retry_chunk(file_job, chunk_index)
