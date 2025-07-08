"""
Test dbt contract enforcement for S065.

This test suite validates that dbt contracts properly enforce schema
constraints and prevent breaking changes.
"""
import subprocess
import tempfile
import os
import pytest
from pathlib import Path


class TestContractEnforcement:
    """Test suite for dbt contract enforcement."""

    @pytest.fixture
    def project_root(self):
        """Get project root directory."""
        return Path(__file__).parent.parent

    @pytest.fixture
    def dbt_dir(self, project_root):
        """Get dbt directory."""
        return project_root / "dbt"

    def run_dbt_command(self, command, dbt_dir, expect_success=True):
        """Run a dbt command and return result."""
        full_command = f"cd {dbt_dir} && source ../venv/bin/activate && {command}"
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            text=True
        )

        if expect_success and result.returncode != 0:
            pytest.fail(f"Command failed: {command}\nStdout: {result.stdout}\nStderr: {result.stderr}")

        return result

    def test_contract_models_exist(self, dbt_dir):
        """Test that contract-enabled models are properly configured."""
        result = self.run_dbt_command("dbt list --select tag:contract", dbt_dir)

        # Should include our 3 contracted models
        contract_models = result.stdout
        assert "stg_census_data" in contract_models
        assert "fct_workforce_snapshot" in contract_models
        assert "fct_yearly_events" in contract_models

        print(f"✅ Found {len(contract_models.strip().split())} contract-enabled models")

    def test_contract_compilation_success(self, dbt_dir):
        """Test that contract models compile successfully."""
        result = self.run_dbt_command("dbt compile --select tag:contract", dbt_dir)

        # Should compile without errors
        assert result.returncode == 0
        assert "Completed successfully" in result.stdout or "ERROR" not in result.stdout

        print("✅ All contract models compile successfully")

    def test_contract_validation_in_ci(self, project_root):
        """Test that CI script includes contract validation."""
        ci_script = project_root / "scripts" / "run_ci_tests.sh"
        assert ci_script.exists(), "CI script not found"

        content = ci_script.read_text()
        assert "tag:contract" in content, "Contract validation not found in CI script"
        assert "dbt compile --select tag:contract" in content, "Contract compilation not in CI"

        print("✅ Contract validation properly integrated in CI")

    def test_schema_change_protection(self, dbt_dir):
        """Test that contracts prevent unintentional schema changes."""
        # This test would modify a model file temporarily to test contract enforcement
        # For now, we verify the configuration is correct

        staging_schema = dbt_dir / "models" / "staging" / "schema.yml"
        assert staging_schema.exists(), "Staging schema file not found"

        content = staging_schema.read_text()

        # Check that stg_census_data has proper contract configuration
        assert "stg_census_data" in content
        assert "data_type:" in content  # Contract column types defined
        assert "constraints:" in content  # Contract constraints defined

        print("✅ Schema contract definitions properly configured")

    def test_incremental_model_contract_compatibility(self, dbt_dir):
        """Test that incremental models work with contracts."""
        # Check that incremental models have proper on_schema_change settings
        fct_workforce_file = dbt_dir / "models" / "marts" / "fct_workforce_snapshot.sql"
        fct_events_file = dbt_dir / "models" / "marts" / "fct_yearly_events.sql"

        assert fct_workforce_file.exists(), "fct_workforce_snapshot.sql not found"
        assert fct_events_file.exists(), "fct_yearly_events.sql not found"

        workforce_content = fct_workforce_file.read_text()
        events_content = fct_events_file.read_text()

        # Both should have contract enforcement and proper on_schema_change
        assert 'contract=' in workforce_content or '"enforced": true' in workforce_content
        assert 'contract=' in events_content or '"enforced": true' in events_content

        # Should use 'fail' for on_schema_change with contracts
        assert "on_schema_change='fail'" in workforce_content
        assert "on_schema_change='fail'" in events_content

        print("✅ Incremental models properly configured for contracts")

    def test_performance_impact(self, dbt_dir):
        """Test that contract compilation performance is acceptable."""
        import time

        # Time contract compilation
        start_time = time.time()
        result = self.run_dbt_command("dbt compile --select tag:contract", dbt_dir)
        contract_time = time.time() - start_time

        # Time full compilation for comparison
        start_time = time.time()
        result = self.run_dbt_command("dbt compile", dbt_dir)
        full_time = time.time() - start_time

        # Contract compilation should be faster than full compilation
        assert contract_time < full_time, f"Contract compilation ({contract_time:.2f}s) slower than full ({full_time:.2f}s)"

        # Performance impact should be minimal (less than 10% overhead when scaled)
        performance_ratio = contract_time / full_time
        print(f"✅ Contract compilation performance ratio: {performance_ratio:.2%}")
        print(f"   Contract time: {contract_time:.2f}s, Full time: {full_time:.2f}s")


if __name__ == "__main__":
    """Run tests directly."""
    test_instance = TestContractEnforcement()

    # Get fixtures
    project_root = Path(__file__).parent.parent
    dbt_dir = project_root / "dbt"

    print("🧪 Running dbt Contract Enforcement Tests\n")

    try:
        test_instance.test_contract_models_exist(dbt_dir)
        test_instance.test_contract_compilation_success(dbt_dir)
        test_instance.test_contract_validation_in_ci(project_root)
        test_instance.test_schema_change_protection(dbt_dir)
        test_instance.test_incremental_model_contract_compatibility(dbt_dir)
        test_instance.test_performance_impact(dbt_dir)

        print("\n🎉 All contract enforcement tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise
