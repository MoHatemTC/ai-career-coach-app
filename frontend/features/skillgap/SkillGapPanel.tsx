/**
 * SkillGapPanel Component
 *
 * Displays skill gap analysis results to users, showing:
 * - Overall match percentage for the target role
 * - Skills they already have (matches)
 * - Prioritized list of missing skills (gaps)
 * - Learning recommendations
 *
 * This is a React/TypeScript component that integrates with the backend
 * skill-gap analysis API.
 */

import React, { useState, useEffect } from 'react';

// Type definitions matching the backend schemas
interface SkillEntry {
  name: string;
  proficiency: 'beginner' | 'intermediate' | 'advanced' | 'expert';
  years_of_experience?: number;
  last_used?: string;
}

interface Profile {
  user_id?: string;
  full_name?: string;
  current_role?: string;
  experience_level: string;
  target_roles: string[];
  skills: SkillEntry[];
  preferred_locations: string[];
  work_type_preferences: string[];
  salary_expectations?: string;
  career_goals?: string;
}

interface SkillRequirement {
  name: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  market_demand?: number;
}

interface GapItem {
  skill_name: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  gap_reason: string;
  current_proficiency?: string;
  recommended_proficiency: string;
  suggested_resources?: string[];
}

interface SkillGap {
  id?: string;
  user_id?: string;
  target_role: string;
  profile_skills: string[];
  required_skills: SkillRequirement[];
  skills_match: string[];
  skill_gaps: GapItem[];
  match_percentage: number;
  critical_gaps_count: number;
  analysis_type: string;
  created_at: string;
  analysis_notes?: string;
}

interface SkillGapPanelProps {
  profile: Profile;
  targetRole?: string;
  onAnalysisComplete?: (gap: SkillGap) => void;
  apiBaseUrl?: string;
}

/**
 * SkillGapPanel - Main component for displaying skill gap analysis
 */
const SkillGapPanel: React.FC<SkillGapPanelProps> = ({
  profile,
  targetRole = profile.target_roles?.[0] || 'Software Engineer',
  onAnalysisComplete,
  apiBaseUrl = '/api'
}) => {
  const [skillGap, setSkillGap] = useState<SkillGap | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedGaps, setExpandedGaps] = useState<Set<string>>(new Set());

  /**
   * Analyze skill gap on component mount or when inputs change
   */
  useEffect(() => {
    const analyzeGap = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(`${apiBaseUrl}/skillgap/analyze`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            profile,
            target_role: targetRole,
            include_market_data: true
          })
        });

        if (!response.ok) {
          throw new Error(`API error: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.success && data.skill_gap) {
          setSkillGap(data.skill_gap);
          onAnalysisComplete?.(data.skill_gap);
        } else {
          setError(data.errors?.[0] || 'Failed to analyze skill gap');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    analyzeGap();
  }, [profile, targetRole, apiBaseUrl, onAnalysisComplete]);

  /**
   * Toggle expansion of a gap item
   */
  const toggleGapExpanded = (skillName: string) => {
    const newExpanded = new Set(expandedGaps);
    if (newExpanded.has(skillName)) {
      newExpanded.delete(skillName);
    } else {
      newExpanded.add(skillName);
    }
    setExpandedGaps(newExpanded);
  };

  /**
   * Get color class for priority level
   */
  const getPriorityColor = (priority: string): string => {
    switch (priority) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'high':
        return 'bg-orange-100 text-orange-800 border-orange-300';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  /**
   * Get priority badge component
   */
  const PriorityBadge: React.FC<{ priority: string }> = ({ priority }) => (
    <span className={`inline-block px-3 py-1 text-sm font-semibold rounded border ${getPriorityColor(priority)}`}>
      {priority.charAt(0).toUpperCase() + priority.slice(1)}
    </span>
  );

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-600">Analyzing your skill gap...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-red-800 mb-2">Analysis Error</h3>
        <p className="text-red-700">{error}</p>
      </div>
    );
  }

  if (!skillGap) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6">
        <p className="text-gray-600">No skill gap data available</p>
      </div>
    );
  }

  return (
    <div className="w-full bg-white rounded-lg shadow-lg p-8">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-800 mb-2">Skill Gap Analysis</h2>
        <p className="text-gray-600">
          Analyzing your readiness for the role of: <span className="font-semibold text-blue-600">{skillGap.target_role}</span>
        </p>
      </div>

      {/* Match Score Section */}
      <div className="mb-8 p-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="text-lg font-semibold text-gray-800 mb-2">Overall Match</h3>
            <p className="text-gray-600">
              You have {skillGap.skills_match.length} out of {skillGap.required_skills.length} required skills
            </p>
          </div>
          <div className="text-right">
            <div className="text-4xl font-bold text-blue-600 mb-1">{skillGap.match_percentage.toFixed(1)}%</div>
            <p className="text-sm text-gray-600">Match percentage</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-gray-300 rounded-full h-3 overflow-hidden">
          <div
            className="bg-gradient-to-r from-blue-500 to-indigo-600 h-full rounded-full transition-all duration-500"
            style={{ width: `${skillGap.match_percentage}%` }}
          ></div>
        </div>
      </div>

      {/* Skills Match Section */}
      {skillGap.skills_match.length > 0 && (
        <div className="mb-8">
          <h3 className="text-xl font-semibold text-gray-800 mb-4 flex items-center">
            <span className="text-2xl mr-2">✓</span>
            Your Matching Skills ({skillGap.skills_match.length})
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {skillGap.skills_match.map((skill) => (
              <div key={skill} className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
                <p className="font-semibold text-gray-800">{skill}</p>
                <p className="text-xs text-green-600 mt-1">You have this skill</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Skill Gaps Section */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-semibold text-gray-800 flex items-center">
            <span className="text-2xl mr-2">!</span>
            Your Skill Gaps ({skillGap.skill_gaps.length})
          </h3>
          {skillGap.critical_gaps_count > 0 && (
            <span className="bg-red-100 text-red-800 px-3 py-1 rounded-full text-sm font-semibold">
              {skillGap.critical_gaps_count} critical
            </span>
          )}
        </div>

        {skillGap.skill_gaps.length === 0 ? (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-green-700 font-semibold">🎉 Great news! You have all the required skills for this role.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {skillGap.skill_gaps.map((gap) => (
              <GapItemCard
                key={gap.skill_name}
                gap={gap}
                expanded={expandedGaps.has(gap.skill_name)}
                onToggle={() => toggleGapExpanded(gap.skill_name)}
                getPriorityColor={getPriorityColor}
                PriorityBadge={PriorityBadge}
              />
            ))}
          </div>
        )}
      </div>

      {/* Analysis Metadata */}
      <div className="text-sm text-gray-500 pt-4 border-t border-gray-200">
        <p>Analysis type: {skillGap.analysis_type}</p>
        <p>Generated: {new Date(skillGap.created_at).toLocaleDateString()}</p>
        {skillGap.analysis_notes && <p>Notes: {skillGap.analysis_notes}</p>}
      </div>
    </div>
  );
};

/**
 * GapItemCard - Component for displaying a single skill gap
 */
interface GapItemCardProps {
  gap: GapItem;
  expanded: boolean;
  onToggle: () => void;
  getPriorityColor: (priority: string) => string;
  PriorityBadge: React.FC<{ priority: string }>;
}

const GapItemCard: React.FC<GapItemCardProps> = ({
  gap,
  expanded,
  onToggle,
  getPriorityColor,
  PriorityBadge
}) => (
  <div className="border border-gray-200 rounded-lg overflow-hidden hover:border-gray-300 transition-colors">
    <button
      onClick={onToggle}
      className="w-full p-4 flex justify-between items-center hover:bg-gray-50 transition-colors text-left"
    >
      <div className="flex items-center gap-4 flex-1">
        <span className="text-2xl">{expanded ? '▼' : '▶'}</span>
        <div>
          <h4 className="font-semibold text-gray-800">{gap.skill_name}</h4>
          <p className="text-sm text-gray-600">{gap.gap_reason}</p>
        </div>
      </div>
      <PriorityBadge priority={gap.priority} />
    </button>

    {expanded && (
      <div className="bg-gray-50 border-t border-gray-200 p-4 space-y-4">
        {/* Current vs Recommended Proficiency */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Your Level</p>
            <p className="text-gray-600">
              {gap.current_proficiency
                ? gap.current_proficiency.charAt(0).toUpperCase() + gap.current_proficiency.slice(1)
                : 'Not yet started'}
            </p>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Recommended Level</p>
            <p className="text-blue-600 font-semibold">
              {gap.recommended_proficiency.charAt(0).toUpperCase() + gap.recommended_proficiency.slice(1)}
            </p>
          </div>
        </div>

        {/* Learning Resources */}
        {gap.suggested_resources && gap.suggested_resources.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-2">Suggested Learning Resources</p>
            <ul className="space-y-2">
              {gap.suggested_resources.map((resource, idx) => (
                <li key={idx} className="text-sm text-gray-600 flex items-start">
                  <span className="mr-2">📚</span>
                  <span>{resource}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    )}
  </div>
);

export default SkillGapPanel;
export type { SkillGap, Profile, GapItem };
