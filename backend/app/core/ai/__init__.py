"""AI infrastructure: LLM provider abstraction, DeepSeek implementation,
prompt template management, and a provider factory.

Business modules depend only on the abstract :class:`LLMProvider` interface
and the prompt manager, keeping them decoupled from any specific AI vendor.
"""
