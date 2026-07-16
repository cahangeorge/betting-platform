import { ApiClient } from './client';

export type GovernanceEvaluation = {
	id: number;
	model_version_id: number;
	evaluation_kind: 'walk_forward' | 'paper';
	status: 'pending' | 'running' | 'passed' | 'failed' | 'insufficient_evidence';
	scope_key: string;
	sample_size: number;
	resolved_count: number;
	valid_folds: number;
	coverage: number | null;
	metrics: Record<string, unknown> | null;
	failure_reasons: string[] | Record<string, unknown> | null;
	created_at: string;
};

export type GovernanceCertification = {
	id: number;
	model_version_id: number;
	model_evaluation_id: number;
	certification_type: 'walk_forward' | 'paper';
	status: 'walk_forward_passed' | 'paper_collecting' | 'certified' | 'suspended' | 'expired';
	scope_key: string;
	valid_from: string;
	valid_until: string;
	suspension_reason: string | null;
};

export type GovernanceMonitoring = {
	id: number;
	model_version_id: number;
	scope_key: string;
	window_started_at: string;
	window_ended_at: string;
	sample_size: number;
	severity: 'healthy' | 'warning' | 'critical' | 'insufficient_evidence';
	metrics: Record<string, unknown>;
	reasons: string[] | Record<string, unknown> | null;
};

export type GovernanceEvidence = {
	model_version: {
		id: number;
		model_key: string;
		version: string;
		build_revision: string;
		engine_version: string | null;
		feature_schema_hash: string;
		strategy_config_hash: string;
		training_data_fingerprint: string;
		training_cutoff_at: string;
		status: string;
	};
	latest_evaluation: GovernanceEvaluation | null;
	latest_certification: GovernanceCertification | null;
	latest_monitoring: GovernanceMonitoring | null;
	gate: {
		analysis_allowed: boolean;
		manual_paper_allowed: boolean;
		scheduled_paper_allowed: boolean;
		reason: string;
		certification_status: GovernanceCertification['status'] | null;
	};
};

type Page<T> = { items: T[]; total: number };

class ModelGovernanceApi extends ApiClient {
	getEvaluations(): Promise<Page<GovernanceEvaluation>> {
		return this.get('/api/v1/model-governance/evaluations?limit=100');
	}

	getCertifications(): Promise<Page<GovernanceCertification>> {
		return this.get('/api/v1/model-governance/certifications?limit=100');
	}

	getMonitoring(): Promise<Page<GovernanceMonitoring>> {
		return this.get('/api/v1/model-governance/monitoring?limit=100');
	}

	getEvidence(modelVersionId: number): Promise<GovernanceEvidence> {
		return this.get(`/api/v1/model-governance/evidence/${modelVersionId}`);
	}
}

export const modelGovernanceApi = new ModelGovernanceApi();
