#!/usr/bin/env python3
"""
EquiFlow Wrapper for M4 Integration

Provides convenient functions to build equity-focused cohort selection
flow diagrams from MIMIC-IV or other clinical datasets.

Features:
- Default equity variables (demographics, socioeconomic, outcome)
- Automatic column name matching (e.g., 'gender' or 'sex')
- SMD-based bias detection

Usage:
    from cohort_flow import CohortFlow
    
    cf = CohortFlow(df)  # Auto-detects equity variables
    cf.exclude(df['age'] >= 18, "Age < 18", "Adults")
    cf.summary()
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Union
from equiflow import EquiFlow


# =============================================================================
# DEFAULT EQUITY VARIABLES FOR CLINICAL RESEARCH
# =============================================================================

# Column name aliases (maps concept -> possible column names)
COLUMN_ALIASES = {
    # Demographics
    'gender': ['gender', 'sex'],
    'age': ['anchor_age', 'age', 'admission_age'],
    'race': ['race', 'ethnicity', 'race_ethnicity'],
    
    # Socioeconomic
    'insurance': ['insurance', 'insurance_type', 'payer'],
    'language': ['language', 'primary_language'],
    'marital_status': ['marital_status', 'marital'],
    
    # Clinical
    'los': ['los', 'length_of_stay', 'icu_los', 'hospital_los'],
    
    # Outcome
    'mortality': ['hospital_expire_flag', 'mortality', 'death', 'expired', 'died'],
}

# Default variable types
DEFAULT_CATEGORICAL = ['gender', 'race', 'insurance', 'language', 'marital_status', 'mortality']
DEFAULT_NORMAL = ['age']
DEFAULT_NONNORMAL = ['los']


def find_column(df: pd.DataFrame, concept: str) -> Optional[str]:
    """
    Find actual column name in DataFrame for a given concept.
    
    Args:
        df: DataFrame to search
        concept: Concept name (e.g., 'gender', 'age')
    
    Returns:
        Actual column name if found, None otherwise
    """
    if concept in COLUMN_ALIASES:
        for alias in COLUMN_ALIASES[concept]:
            # Case-insensitive matching
            for col in df.columns:
                if col.lower() == alias.lower():
                    return col
    
    # Direct match (case-insensitive)
    for col in df.columns:
        if col.lower() == concept.lower():
            return col
    
    return None


def get_default_variables(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Get default equity variables that exist in the DataFrame.
    
    Args:
        df: Input DataFrame
        
    Returns:
        Dict with 'categorical', 'normal', 'nonnormal' lists
    """
    categorical = []
    normal = []
    nonnormal = []
    
    # Find categorical variables
    for concept in DEFAULT_CATEGORICAL:
        col = find_column(df, concept)
        if col:
            categorical.append(col)
    
    # Find normal continuous variables
    for concept in DEFAULT_NORMAL:
        col = find_column(df, concept)
        if col:
            normal.append(col)
    
    # Find non-normal continuous variables
    for concept in DEFAULT_NONNORMAL:
        col = find_column(df, concept)
        if col:
            nonnormal.append(col)
    
    return {
        'categorical': categorical,
        'normal': normal,
        'nonnormal': nonnormal
    }


class CohortFlow:
    """
    Equity-focused cohort selection flow diagram generator.
    
    Tracks demographic and socioeconomic variable distributions
    across exclusion steps to detect potential selection bias.
    """
    
    def __init__(
        self,
        data: pd.DataFrame,
        categorical: Optional[List[str]] = None,
        normal: Optional[List[str]] = None,
        nonnormal: Optional[List[str]] = None,
        additional: Optional[List[str]] = None,
        use_defaults: bool = True,
        initial_label: str = "Initial cohort"
    ):
        """
        Initialize CohortFlow.
        
        Args:
            data: Input DataFrame
            categorical: Categorical variables to track (overrides defaults)
            normal: Normally distributed continuous variables (overrides defaults)
            nonnormal: Non-normally distributed continuous variables (overrides defaults)
            additional: Additional variables to add to defaults
            use_defaults: Whether to use default equity variables when none specified
            initial_label: Label for the initial cohort
            
        Default equity variables (if use_defaults=True and no variables specified):
            - categorical: gender, race, insurance, language, marital_status, mortality
            - normal: age
            - nonnormal: los
        """
        self.data = data.copy()
        self.current_data = data.copy()
        self.exclusions = []
        
        # Determine which variables to track
        if categorical is None and normal is None and nonnormal is None:
            if use_defaults:
                # Use default equity variables
                defaults = get_default_variables(data)
                self.categorical = defaults['categorical']
                self.normal = defaults['normal']
                self.nonnormal = defaults['nonnormal']
                
                if not any([self.categorical, self.normal, self.nonnormal]):
                    print("⚠️ Warning: No default equity variables found in DataFrame.")
                    print(f"   Available columns: {list(data.columns)}")
                    print(f"   Expected: gender/sex, age, race, insurance, etc.")
            else:
                self.categorical = []
                self.normal = []
                self.nonnormal = []
        else:
            # Use user-specified variables
            self.categorical = categorical or []
            self.normal = normal or []
            self.nonnormal = nonnormal or []
        
        # Add additional variables if specified
        if additional:
            for var in additional:
                if var in data.columns:
                    # Auto-detect type
                    if data[var].dtype == 'object' or data[var].nunique() <= 10:
                        if var not in self.categorical:
                            self.categorical.append(var)
                    else:
                        if var not in self.normal and var not in self.nonnormal:
                            # Check skewness
                            skew = data[var].skew()
                            if abs(skew) < 1:
                                self.normal.append(var)
                            else:
                                self.nonnormal.append(var)
        
        # Initialize EquiFlow
        self.flow = EquiFlow(
            data=data,
            categorical=self.categorical if self.categorical else None,
            normal=self.normal if self.normal else None,
            nonnormal=self.nonnormal if self.nonnormal else None,
            initial_cohort_label=initial_label
        )
        
        # Store tracking info
        self._tracked_vars = {
            'categorical': self.categorical,
            'normal': self.normal,
            'nonnormal': self.nonnormal
        }
    
    def tracked_variables(self) -> Dict[str, List[str]]:
        """Return the variables being tracked for equity analysis."""
        return self._tracked_vars
    
    def exclude(
        self,
        keep_mask: pd.Series,
        reason: str,
        new_label: str
    ) -> 'CohortFlow':
        """
        Add an exclusion criterion.
        
        Args:
            keep_mask: Boolean Series (True = keep, False = exclude)
            reason: Description of why patients were excluded
            new_label: Label for the resulting cohort
            
        Returns:
            self for method chaining
        """
        # Align mask with current data index
        aligned_mask = keep_mask.reindex(self.current_data.index, fill_value=False)
        
        n_before = len(self.current_data)
        n_excluded = (~aligned_mask).sum()
        
        self.exclusions.append({
            'reason': reason,
            'label': new_label,
            'n_excluded': int(n_excluded),
            'n_remaining': int(n_before - n_excluded)
        })
        
        self.flow.add_exclusion(
            keep=keep_mask,
            exclusion_reason=reason,
            new_cohort_label=new_label
        )
        
        self.current_data = self.current_data[aligned_mask]
        
        return self
    
    def summary(self) -> Dict:
        """
        Get summary of all exclusion steps.
        
        Returns:
            Dictionary with flow_table, characteristics, and drifts
        """
        return {
            'tracked_variables': self._tracked_vars,
            'flow_table': self.flow.view_table_flows(),
            'characteristics': self.flow.view_table_characteristics(),
            'drifts': self.flow.view_table_drifts()
        }
    
    def view_flows(self) -> pd.DataFrame:
        """View the flow table (N at each step)."""
        return self.flow.view_table_flows()
    
    def view_characteristics(self) -> pd.DataFrame:
        """View the characteristics table."""
        return self.flow.view_table_characteristics()
    
    def view_drifts(self) -> pd.DataFrame:
        """View the SMD drifts table."""
        return self.flow.view_table_drifts()
    
    def check_bias(self, threshold: float = 0.2) -> pd.DataFrame:
        """
        Check for potential selection bias (SMD > threshold).
        
        Args:
            threshold: SMD threshold for flagging bias (default 0.2)
            
        Returns:
            DataFrame of variables with |SMD| > threshold at any step
        """
        drifts = self.flow.view_table_drifts()
        
        if drifts.empty:
            print("⚠️ No variables tracked. Cannot check bias.")
            return pd.DataFrame()
        
        flagged = []
        for var in drifts.index:
            for col in drifts.columns:
                try:
                    smd = float(drifts.loc[var, col])
                    if abs(smd) > threshold:
                        flagged.append({
                            'variable': var,
                            'step': col,
                            'smd': round(smd, 3),
                            'concern': 'High' if abs(smd) > 0.3 else 'Moderate'
                        })
                except:
                    pass
        
        if flagged:
            return pd.DataFrame(flagged).sort_values('smd', key=abs, ascending=False)
        else:
            print(f"✓ No variables with |SMD| > {threshold}")
            return pd.DataFrame()
    
    def plot(
        self,
        output_file: str = "cohort_flow",
        output_folder: str = ".",
        show_smds: bool = True,
        **kwargs
    ) -> str:
        """
        Generate flow diagram.
        
        Args:
            output_file: Output filename (without extension)
            output_folder: Output directory
            show_smds: Whether to show SMD values
            **kwargs: Additional arguments for plot_flows()
            
        Returns:
            Path to generated file
        """
        self.flow.plot_flows(
            output_file=output_file,
            output_folder=output_folder,
            smds=show_smds,
            display_flow_diagram=False,
            **kwargs
        )
        output_path = f"{output_folder}/{output_file}.pdf"
        print(f"✓ Flow diagram saved to {output_path}")
        return output_path
    
    def get_final_cohort(self) -> pd.DataFrame:
        """Return the final cohort after all exclusions."""
        return self.current_data.copy()
    
    def __repr__(self) -> str:
        n_initial = len(self.data)
        n_final = len(self.current_data)
        n_steps = len(self.exclusions)
        n_vars = len(self.categorical) + len(self.normal) + len(self.nonnormal)
        return (
            f"CohortFlow(\n"
            f"  n_initial={n_initial:,}, n_final={n_final:,},\n"
            f"  exclusion_steps={n_steps},\n"
            f"  tracked_variables={n_vars} "
            f"(categorical={len(self.categorical)}, "
            f"normal={len(self.normal)}, "
            f"nonnormal={len(self.nonnormal)})\n"
            f")"
        )


def quick_flow(
    df: pd.DataFrame,
    exclusions: List[tuple],
    categorical: Optional[List[str]] = None,
    normal: Optional[List[str]] = None,
    nonnormal: Optional[List[str]] = None,
    output_file: Optional[str] = None
) -> CohortFlow:
    """
    Quick function to create cohort flow in one call.
    
    Args:
        df: Input DataFrame
        exclusions: List of (mask, reason, label) tuples
        categorical: Categorical variables (or use defaults)
        normal: Normal continuous variables (or use defaults)
        nonnormal: Non-normal continuous variables (or use defaults)
        output_file: If provided, save flow diagram
        
    Returns:
        CohortFlow object with results
        
    Example:
        cf = quick_flow(
            df,
            exclusions=[
                (df['age'] >= 18, "Age < 18", "Adults"),
                (df['los'] >= 24, "LOS < 24h", "LOS ≥ 24h"),
            ]
        )
    """
    cf = CohortFlow(
        df, 
        categorical=categorical,
        normal=normal,
        nonnormal=nonnormal
    )
    
    for keep_mask, reason, label in exclusions:
        cf.exclude(keep_mask, reason, label)
    
    if output_file:
        cf.plot(output_file)
    
    return cf


# =============================================================================
# CLI / TEST
# =============================================================================

if __name__ == "__main__":
    # Simulate MIMIC-IV style data
    np.random.seed(42)
    n = 1000
    
    df = pd.DataFrame({
        'subject_id': range(n),
        'anchor_age': np.random.normal(65, 15, n),
        'gender': np.random.choice(['M', 'F'], n),
        'race': np.random.choice(['WHITE', 'BLACK', 'ASIAN', 'HISPANIC', 'OTHER'], n, 
                                  p=[0.55, 0.2, 0.1, 0.1, 0.05]),
        'insurance': np.random.choice(['Medicare', 'Medicaid', 'Private', 'Self Pay'], n,
                                       p=[0.5, 0.2, 0.25, 0.05]),
        'language': np.random.choice(['ENGLISH', 'SPANISH', 'OTHER'], n, p=[0.85, 0.1, 0.05]),
        'marital_status': np.random.choice(['MARRIED', 'SINGLE', 'WIDOWED', 'DIVORCED'], n),
        'los': np.random.exponential(5, n),
        'hospital_expire_flag': np.random.choice([0, 1], n, p=[0.9, 0.1])
    })
    
    print("=" * 60)
    print("EQUIFLOW SKILL TEST - MIMIC-IV Style Data")
    print("=" * 60)
    
    # Test 1: Default variables (no specification)
    print("\n[Test 1] Using default equity variables:")
    cf = CohortFlow(df)
    print(cf)
    print(f"Tracked: {cf.tracked_variables()}")
    
    # Add exclusions
    cf.exclude(df['anchor_age'] >= 18, "Age < 18 years", "Adult patients")
    cf.exclude(df['los'] >= 1, "LOS < 24 hours", "Admitted ≥ 24h")
    
    print("\n=== Flow Table ===")
    print(cf.view_flows())
    
    print("\n=== SMD Drifts ===")
    print(cf.view_drifts())
    
    print("\n=== Bias Check (SMD > 0.1) ===")
    bias = cf.check_bias(threshold=0.1)
    if not bias.empty:
        print(bias)
    
    # Test 2: User-specified variables
    print("\n" + "=" * 60)
    print("[Test 2] User-specified variables only:")
    cf2 = CohortFlow(
        df,
        categorical=['gender', 'race'],
        normal=['anchor_age'],
        use_defaults=False
    )
    print(f"Tracked: {cf2.tracked_variables()}")
    
    # Test 3: Defaults + additional
    print("\n" + "=" * 60)
    print("[Test 3] Defaults + additional variable:")
    cf3 = CohortFlow(df, additional=['subject_id'])
    print(f"Tracked: {cf3.tracked_variables()}")
