from pathlib import Path

from core.command import CommandState


class TestCommandState:

    def test_save_load_remove(self, tmp_path: Path):
        filename = tmp_path / 'state'
        state = 'THE_STATE'
        cs = CommandState(str(filename))
        cs.set_state(state)
        assert filename.exists()
        assert cs.get_state() == state
        cs.unset_state()
        assert not filename.exists()
        assert cs.get_state() is None
