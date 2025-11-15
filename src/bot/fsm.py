"""FSM states for the generation workflow."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class GenerationStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_category = State()
    waiting_for_prompt = State()
    waiting_for_parameters = State()
    waiting_for_confirmation = State()
    displaying_result = State()
