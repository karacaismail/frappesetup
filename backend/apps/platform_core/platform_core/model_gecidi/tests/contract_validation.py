"""Read and validate model gateway API responses against the tracked OpenAPI contract."""

from pathlib import Path
from urllib.parse import quote

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

CONTRACT_IRI = "urn:platform-core:model-gateway"


class GatewayContract:
	def __init__(self):
		here = Path(__file__).resolve()
		filename = "platform_core-model-gecidi.openapi.yaml"
		contract_file = here.parents[3] / "contracts" / filename
		if not contract_file.is_file():
			contract_file = here.parents[5] / "contracts" / filename
		self.spec = yaml.safe_load(contract_file.read_text(encoding="utf-8"))
		self.registry = Registry().with_resource(CONTRACT_IRI, DRAFT202012.create_resource(self.spec))

	def response(self, path, method, status):
		parts = ["paths", path, method.lower(), "responses", str(status)]
		response = self.spec["paths"][path][method.lower()]["responses"][str(status)]
		if "$ref" in response:
			parts = response["$ref"].removeprefix("#/").split("/")
			response = self.spec
			for part in parts:
				response = response[part]
		pointer = "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)
		media = response["content"]["application/json"]
		return media, f"{CONTRACT_IRI}#/{quote(pointer)}/content/application~1json/schema"

	def validate_response(self, path, method, status, payload):
		_media, schema = self.response(path, method, status)
		Draft202012Validator({"$ref": schema}, registry=self.registry).validate(payload)

	def validate_completion_cost(self, payload):
		path = "/api/method/platform_core.api.model.resolve_usage".replace("/", "~1")
		schema = f"{CONTRACT_IRI}#/paths/{path}/post/requestBody/content/application~1json/schema"
		Draft202012Validator({"$ref": schema}, registry=self.registry).validate(payload)
