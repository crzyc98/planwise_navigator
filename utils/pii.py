# filename: planwise_navigator/utils/pii.py
"""PII masking utilities for data protection."""

import hashlib
import random
import string
from typing import Dict, List, Optional, Any
import pandas as pd
from functools import lru_cache

class PIIMasker:
    """Handle PII masking for exports and non-privileged users."""
    
    def __init__(self, salt: str = "planwise_default_salt"):
        self.salt = salt
        self.masked_columns = {
            'first_name', 'last_name', 'email', 'ssn', 
            'phone', 'address', 'employee_name'
        }
        self.partial_mask_columns = {'employee_id'}
    
    @lru_cache(maxsize=10000)
    def hash_value(self, value: str) -> str:
        """Generate consistent hash for a value."""
        if pd.isna(value) or value == '':
            return value
        
        hash_input = f"{self.salt}:{value}".encode('utf-8')
        hash_output = hashlib.sha256(hash_input).hexdigest()
        return hash_output[:8].upper()
    
    def mask_email(self, email: str) -> str:
        """Mask email while preserving domain."""
        if pd.isna(email) or '@' not in email:
            return email
        
        local, domain = email.split('@', 1)
        masked_local = self.hash_value(local).lower()[:6]
        return f"{masked_local}@{domain}"
    
    def mask_name(self, name: str) -> str:
        """Mask name while preserving format."""
        if pd.isna(name):
            return name
        
        # Preserve first letter and length hint
        first_letter = name[0] if name else 'X'
        length_category = 'S' if len(name) < 5 else 'M' if len(name) < 10 else 'L'
        return f"{first_letter}_{length_category}_{self.hash_value(name)[:4]}"
    
    def partial_mask_id(self, employee_id: str) -> str:
        """Partially mask ID, keeping prefix."""
        if pd.isna(employee_id) or len(employee_id) < 4:
            return employee_id
        
        prefix = employee_id[:2]
        suffix = 'X' * (len(employee_id) - 2)
        return f"{prefix}{suffix}"
    
    def mask_dataframe(
        self, 
        df: pd.DataFrame, 
        custom_rules: Optional[Dict[str, str]] = None
    ) -> pd.DataFrame:
        """Apply PII masking to entire DataFrame."""
        df_masked = df.copy()
        
        # Apply default masking rules
        for col in df_masked.columns:
            col_lower = col.lower()
            
            if col_lower in self.masked_columns:
                if 'email' in col_lower:
                    df_masked[col] = df_masked[col].apply(self.mask_email)
                elif 'name' in col_lower:
                    df_masked[col] = df_masked[col].apply(self.mask_name)
                else:
                    df_masked[col] = df_masked[col].apply(lambda x: self.hash_value(str(x)))
            
            elif col_lower in self.partial_mask_columns:
                df_masked[col] = df_masked[col].apply(self.partial_mask_id)
        
        # Apply custom rules
        if custom_rules:
            for col, rule in custom_rules.items():
                if col in df_masked.columns:
                    if rule == 'remove':
                        df_masked = df_masked.drop(columns=[col])
                    elif rule == 'randomize':
                        df_masked[col] = self._randomize_column(df_masked[col])
        
        return df_masked
    
    def _randomize_column(self, series: pd.Series) -> pd.Series:
        """Randomize values while preserving data type and distribution."""
        if series.dtype in ['int64', 'float64']:
            # Preserve statistical properties
            mean = series.mean()
            std = series.std()
            return pd.Series(
                [random.gauss(mean, std) for _ in range(len(series))],
                index=series.index
            )
        else:
            # Random strings
            return pd.Series(
                [''.join(random.choices(string.ascii_letters, k=8)) for _ in range(len(series))],
                index=series.index
            )
    
    def get_masking_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate report of what would be masked."""
        report = {
            'total_rows': len(df),
            'columns_to_mask': [],
            'columns_to_partial_mask': [],
            'pii_risk_score': 0
        }
        
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in self.masked_columns:
                report['columns_to_mask'].append(col)
                report['pii_risk_score'] += 10
            elif col_lower in self.partial_mask_columns:
                report['columns_to_partial_mask'].append(col)
                report['pii_risk_score'] += 5
            
            # Check for potential PII patterns
            if any(term in col_lower for term in ['ssn', 'social', 'tax', 'id', 'birth']):
                report['pii_risk_score'] += 3
        
        report['risk_level'] = (
            'High' if report['pii_risk_score'] > 30 else
            'Medium' if report['pii_risk_score'] > 15 else
            'Low'
        )
        
        return report

# Example usage functions
def mask_for_export(df: pd.DataFrame, user_role: str = 'analyst') -> pd.DataFrame:
    """Apply appropriate masking based on user role."""
    masker = PIIMasker()
    
    if user_role == 'admin':
        # No masking for admins
        return df
    elif user_role == 'analyst':
        # Partial masking
        return masker.mask_dataframe(df, custom_rules={'ssn': 'remove'})
    else:
        # Full masking for other roles
        return masker.mask_dataframe(
            df, 
            custom_rules={
                'ssn': 'remove',
                'email': 'remove',
                'phone': 'remove'
            }
        )

def validate_no_pii(df: pd.DataFrame) -> bool:
    """Check if DataFrame contains potential PII."""
    masker = PIIMasker()
    report = masker.get_masking_report(df)
    return report['risk_level'] == 'Low'