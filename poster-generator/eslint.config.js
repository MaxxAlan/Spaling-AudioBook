import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist/**', 'coverage/**', 'output/**', '.story-thumbnail/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ['src/**/*.ts', 'tests/**/*.ts'], rules: { '@typescript-eslint/no-explicit-any': 'off' } }
);
