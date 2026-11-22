"""Keep a redacted numeric balance out of document responses."""

BALANCE_FIELD = "leave_balance"


class LeaveApplication:
	def apply_fieldlevel_read_permissions(self):
		super().apply_fieldlevel_read_permissions()
		self.flags.cronhr_balance_redacted = not hasattr(self, BALANCE_FIELD)

	def as_dict(self, *args, **kwargs):
		data = super().as_dict(*args, **kwargs)
		# Frappe serializes a deleted Float attribute as 0.0.
		if self.flags.cronhr_balance_redacted:
			data.pop(BALANCE_FIELD, None)
		return data
