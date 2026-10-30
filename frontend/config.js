// Public configuration for this build-free frontend. Never put credentials here.
export const API_BASE_URL = 'http://127.0.0.1:8001';

// Model context budget; backend independently applies its environment limits.
export const CONTEXT_LIMITS = { messages: 200, characters: 60000, perMessage: 10000 };
