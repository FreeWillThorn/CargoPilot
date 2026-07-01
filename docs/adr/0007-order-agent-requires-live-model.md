# Order Agent Requires a Live Model

CargoPilot's `订单智能体` MVP will require a live configured model call for task understanding and risk prompting. If the model is unavailable, unconfigured, times out, or returns unusable structured output, the run must fail clearly and must not generate local fallback risk findings or data-entry applications that pretend to be model results. Local file parsing may prepare source text or attachment summaries for the model, but the Order Agent cannot produce user-facing agent conclusions without a successful live model response.
