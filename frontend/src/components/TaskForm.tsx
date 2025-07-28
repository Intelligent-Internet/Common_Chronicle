import React, { useState, useEffect } from 'react';
import type {
  TaskFormData,
  DataSourceCheckboxState,
  DataSourceIdentifier,
  TaskConfigOptions,
} from '../types';
import { getCheckboxStateFromString, getDataSourcePreferenceString } from '../utils/timelineUtils';
import { getTaskConfigOptions } from '../services/api';
import { useAuth } from '../contexts/auth';

interface TaskFormProps {
  onSubmit: (formData: TaskFormData) => void;
  isSubmitting: boolean;
  error: string | null;
}

const TaskForm: React.FC<TaskFormProps> = ({ onSubmit, isSubmitting, error }) => {
  const { user } = useAuth();
  const [topic, setTopic] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [dataSources, setDataSources] = useState<DataSourceCheckboxState>(
    getCheckboxStateFromString('dataset_wikipedia_en=true')
  );

  // Advanced configuration state
  const [showAdvancedConfig, setShowAdvancedConfig] = useState(false);
  const [configOptions, setConfigOptions] = useState<TaskConfigOptions | null>(null);
  const [advancedConfig, setAdvancedConfig] = useState({
    article_limit: 10,
    timeline_relevance_threshold: 0.6,
    reuse_composite_viewpoint: true,
    reuse_base_viewpoint: true,
    search_mode: 'hybrid_title_search' as const,
    vector_weight: 0.6,
    bm25_weight: 0.4,
  });

  // Load configuration options from backend
  useEffect(() => {
    const fetchConfigOptions = async () => {
      try {
        console.log('[TaskForm] Loading task configuration options...');
        const options = await getTaskConfigOptions();
        setConfigOptions(options);

        // Set default values from backend
        setAdvancedConfig({
          article_limit: options.article_limit.default,
          timeline_relevance_threshold: options.timeline_relevance_threshold.default,
          reuse_composite_viewpoint: options.reuse_composite_viewpoint.default,
          reuse_base_viewpoint: options.reuse_base_viewpoint.default,
          search_mode: options.search_mode.default as 'semantic' | 'hybrid_title_search',
          vector_weight: options.vector_weight.default,
          bm25_weight: options.bm25_weight.default,
        });
        console.log('[TaskForm] Configuration options loaded successfully');
      } catch (error) {
        console.error('[TaskForm] Failed to load config options:', error);
        // Keep the hardcoded default values as fallback
      }
    };

    fetchConfigOptions();
  }, []);

  const handleDataSourceToggle = (sourceKey: DataSourceIdentifier, checked: boolean) => {
    setDataSources((prev: DataSourceCheckboxState) => ({
      ...prev,
      [sourceKey]: checked,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) {
      // Basic validation, though the 'required' attribute on input is primary
      return;
    }
    const dataSourceString = getDataSourcePreferenceString(dataSources);
    onSubmit({
      topic_text: topic,
      data_source_pref: dataSourceString,
      is_public: user ? isPublic : undefined,
      // Include advanced configuration if advanced panel is shown
      advanced_config: showAdvancedConfig ? advancedConfig : undefined,
    });
  };

  const dataSourceOptions: { key: DataSourceIdentifier; label: string; description: string }[] = [
    {
      key: 'dataset_wikipedia_en',
      label: 'Dataset Wikipedia of English',
      description: 'A vast, locally-stored snapshot of English Wikipedia.',
    },
    {
      key: 'online_wikipedia',
      label: 'Online Wikipedia',
      description:
        'Current, live articles from the global encyclopedia, including the input-language and English articles.',
    },
    {
      key: 'online_wikinews',
      label: 'Online Wikinews',
      description: 'Recent and archived news reports, including the input-language.',
    },
  ];

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      <div>
        <label
          htmlFor="topic"
          className="block text-lg font-sans font-medium text-charcoal dark:text-white mb-2"
        >
          I. Define Your Subject of Inquiry
        </label>
        <p className="text-slate dark:text-mist mb-4">
          Enter the historical topic, event, or question you wish to investigate. Be as specific as
          possible for a more focused chronicle.
        </p>
        <textarea
          id="topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          className="w-full bg-white dark:bg-slate border border-pewter rounded-md p-3 text-charcoal dark:text-mist placeholder-pewter focus:ring-1 focus:ring-slate focus:border-slate dark:focus:ring-sky-blue dark:focus:border-sky-blue transition"
          placeholder="e.g., The economic impact of the Silk Road during the Tang Dynasty"
          required
          disabled={isSubmitting}
          rows={3}
          maxLength={1000}
        />
        <p className="text-right text-xs text-pewter mt-1">{topic.length} / 1000</p>
      </div>

      <div>
        <label className="block text-lg font-sans font-medium text-charcoal dark:text-white mb-2">
          II. Select Primary Sources
        </label>
        <p className="text-slate dark:text-mist mb-4">
          Choose the archives from which to draw information for your chronicle. At least one source
          is required.
        </p>
        <div className="space-y-4">
          {dataSourceOptions.map(({ key, label, description }) => (
            <div
              key={key}
              className="relative flex items-start bg-mist/30 dark:bg-slate/30 p-4 border border-mist dark:border-pewter rounded-lg"
            >
              <div className="flex h-6 items-center">
                <input
                  id={key}
                  name={key}
                  type="checkbox"
                  checked={dataSources[key]}
                  onChange={(e) => handleDataSourceToggle(key, e.target.checked)}
                  disabled={isSubmitting}
                  className="h-5 w-5 rounded border-pewter text-slate dark:text-sky-blue focus:ring-slate dark:focus:ring-sky-blue"
                />
              </div>
              <div className="ml-3 text-sm leading-6">
                <label htmlFor={key} className="font-medium text-charcoal dark:text-white">
                  {label}
                </label>
                <p className="text-slate dark:text-mist">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {user && (
        <div>
          <label className="block text-lg font-sans font-medium text-charcoal dark:text-white mb-2">
            III. Set Visibility
          </label>
          <div className="relative flex items-start bg-mist/30 dark:bg-slate/30 p-4 border border-mist dark:border-pewter rounded-lg">
            <div className="flex h-6 items-center">
              <input
                id="is_public"
                name="is_public"
                type="checkbox"
                checked={isPublic}
                onChange={(e) => setIsPublic(e.target.checked)}
                disabled={isSubmitting}
                className="h-5 w-5 rounded border-pewter text-slate dark:text-sky-blue focus:ring-slate dark:focus:ring-sky-blue"
              />
            </div>
            <div className="ml-3 text-sm leading-6">
              <label htmlFor="is_public" className="font-medium text-charcoal dark:text-white">
                Make this Chronicle Public
              </label>
              <p className="text-slate dark:text-mist">
                Allow anyone to view the generated timeline. If unchecked, it will be private.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* IV. Advanced Configuration */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-lg font-sans font-medium text-charcoal dark:text-white">
            IV. Advanced Configuration
          </label>
          <button
            type="button"
            onClick={() => setShowAdvancedConfig(!showAdvancedConfig)}
            disabled={isSubmitting}
            className="text-sm text-slate dark:text-sky-blue hover:underline focus:outline-none disabled:opacity-50"
          >
            {showAdvancedConfig ? 'Hide' : 'Show'} Advanced Options
          </button>
        </div>

        {showAdvancedConfig && (
          <div className="space-y-6 bg-mist/10 dark:bg-slate/10 p-6 rounded-lg border border-mist dark:border-pewter">
            {/* Article Limit */}
            <div>
              <label className="block text-sm font-medium text-charcoal dark:text-white mb-2">
                Article Limit:{' '}
                <span className="font-mono text-slate dark:text-sky-blue">
                  {advancedConfig.article_limit}
                </span>
              </label>
              <input
                type="range"
                min={configOptions?.article_limit.min || 1}
                max={configOptions?.article_limit.max || 50}
                step={configOptions?.article_limit.step || 1}
                value={advancedConfig.article_limit}
                onChange={(e) =>
                  setAdvancedConfig((prev) => ({
                    ...prev,
                    article_limit: parseInt(e.target.value),
                  }))
                }
                disabled={isSubmitting}
                className="w-full h-2 bg-mist dark:bg-pewter rounded-lg appearance-none cursor-pointer slider"
              />
              <div className="flex justify-between text-xs text-pewter mt-1">
                <span>{configOptions?.article_limit.min || 1}</span>
                <span>{configOptions?.article_limit.max || 50}</span>
              </div>
              <p className="text-xs text-slate dark:text-mist mt-2">
                {configOptions?.article_limit.description ||
                  'Maximum number of articles to process'}
              </p>
            </div>

            {/* Timeline Relevance Threshold */}
            <div>
              <label className="block text-sm font-medium text-charcoal dark:text-white mb-2">
                Relevance Threshold:{' '}
                <span className="font-mono text-slate dark:text-sky-blue">
                  {advancedConfig.timeline_relevance_threshold.toFixed(2)}
                </span>
              </label>
              <input
                type="range"
                min={configOptions?.timeline_relevance_threshold.min || 0}
                max={configOptions?.timeline_relevance_threshold.max || 1}
                step={configOptions?.timeline_relevance_threshold.step || 0.05}
                value={advancedConfig.timeline_relevance_threshold}
                onChange={(e) =>
                  setAdvancedConfig((prev) => ({
                    ...prev,
                    timeline_relevance_threshold: parseFloat(e.target.value),
                  }))
                }
                disabled={isSubmitting}
                className="w-full h-2 bg-mist dark:bg-pewter rounded-lg appearance-none cursor-pointer slider"
              />
              <div className="flex justify-between text-xs text-pewter mt-1">
                <span>{configOptions?.timeline_relevance_threshold.min || 0}</span>
                <span>{configOptions?.timeline_relevance_threshold.max || 1}</span>
              </div>
              <p className="text-xs text-slate dark:text-mist mt-2">
                {configOptions?.timeline_relevance_threshold.description ||
                  'Minimum relevance score for events to include'}
              </p>
            </div>

            {/* Search Mode */}
            <div>
              <label className="block text-sm font-medium text-charcoal dark:text-white mb-2">
                Search Strategy
              </label>
              <select
                value={advancedConfig.search_mode}
                onChange={(e) =>
                  setAdvancedConfig((prev) => ({
                    ...prev,
                    search_mode: e.target.value as 'semantic' | 'hybrid_title_search',
                  }))
                }
                disabled={isSubmitting}
                className="w-full bg-white dark:bg-slate border border-pewter rounded-md p-2 text-charcoal dark:text-mist focus:ring-1 focus:ring-slate focus:border-slate dark:focus:ring-sky-blue dark:focus:border-sky-blue"
              >
                {configOptions?.search_mode.options.map((option) => (
                  <option key={option} value={option}>
                    {option === 'semantic' ? 'Semantic Search' : 'Hybrid Title Search'}
                  </option>
                )) || (
                  <>
                    <option value="semantic">Semantic Search</option>
                    <option value="hybrid_title_search">Hybrid Title Search</option>
                  </>
                )}
              </select>
              <p className="text-xs text-slate dark:text-mist mt-2">
                {configOptions?.search_mode.description ||
                  'Choose between semantic or hybrid search strategy'}
              </p>
            </div>

            {/* Search Weights (only show for hybrid mode) */}
            {advancedConfig.search_mode === 'hybrid_title_search' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-charcoal dark:text-white mb-2">
                    Vector Weight:{' '}
                    <span className="font-mono text-slate dark:text-sky-blue">
                      {advancedConfig.vector_weight.toFixed(1)}
                    </span>
                  </label>
                  <input
                    type="range"
                    min={configOptions?.vector_weight.min || 0}
                    max={configOptions?.vector_weight.max || 1}
                    step={configOptions?.vector_weight.step || 0.1}
                    value={advancedConfig.vector_weight}
                    onChange={(e) =>
                      setAdvancedConfig((prev) => ({
                        ...prev,
                        vector_weight: parseFloat(e.target.value),
                      }))
                    }
                    disabled={isSubmitting}
                    className="w-full h-2 bg-mist dark:bg-pewter rounded-lg appearance-none cursor-pointer slider"
                  />
                  <p className="text-xs text-slate dark:text-mist mt-1">
                    {configOptions?.vector_weight.description ||
                      'Weight for semantic similarity scoring'}
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-charcoal dark:text-white mb-2">
                    BM25 Weight:{' '}
                    <span className="font-mono text-slate dark:text-sky-blue">
                      {advancedConfig.bm25_weight.toFixed(1)}
                    </span>
                  </label>
                  <input
                    type="range"
                    min={configOptions?.bm25_weight.min || 0}
                    max={configOptions?.bm25_weight.max || 1}
                    step={configOptions?.bm25_weight.step || 0.1}
                    value={advancedConfig.bm25_weight}
                    onChange={(e) =>
                      setAdvancedConfig((prev) => ({
                        ...prev,
                        bm25_weight: parseFloat(e.target.value),
                      }))
                    }
                    disabled={isSubmitting}
                    className="w-full h-2 bg-mist dark:bg-pewter rounded-lg appearance-none cursor-pointer slider"
                  />
                  <p className="text-xs text-slate dark:text-mist mt-1">
                    {configOptions?.bm25_weight.description || 'Weight for keyword-based scoring'}
                  </p>
                </div>
              </div>
            )}

            {/* Reuse Options */}
            <div>
              <h4 className="text-sm font-medium text-charcoal dark:text-white mb-3">
                Optimization Settings
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex items-start space-x-3">
                  <input
                    type="checkbox"
                    id="reuse_composite"
                    checked={advancedConfig.reuse_composite_viewpoint}
                    onChange={(e) =>
                      setAdvancedConfig((prev) => ({
                        ...prev,
                        reuse_composite_viewpoint: e.target.checked,
                      }))
                    }
                    disabled={isSubmitting}
                    className="h-4 w-4 mt-1 rounded border-pewter text-slate dark:text-sky-blue focus:ring-slate dark:focus:ring-sky-blue"
                  />
                  <div>
                    <label
                      htmlFor="reuse_composite"
                      className="text-sm font-medium text-charcoal dark:text-white cursor-pointer"
                    >
                      Reuse Synthetic Viewpoints
                    </label>
                    <p className="text-xs text-slate dark:text-mist mt-1">
                      {configOptions?.reuse_composite_viewpoint.description ||
                        'Avoid reprocessing identical topics'}
                    </p>
                  </div>
                </div>

                <div className="flex items-start space-x-3">
                  <input
                    type="checkbox"
                    id="reuse_base"
                    checked={advancedConfig.reuse_base_viewpoint}
                    onChange={(e) =>
                      setAdvancedConfig((prev) => ({
                        ...prev,
                        reuse_base_viewpoint: e.target.checked,
                      }))
                    }
                    disabled={isSubmitting}
                    className="h-4 w-4 mt-1 rounded border-pewter text-slate dark:text-sky-blue focus:ring-slate dark:focus:ring-sky-blue"
                  />
                  <div>
                    <label
                      htmlFor="reuse_base"
                      className="text-sm font-medium text-charcoal dark:text-white cursor-pointer"
                    >
                      Reuse Base Viewpoints
                    </label>
                    <p className="text-xs text-slate dark:text-mist mt-1">
                      {configOptions?.reuse_base_viewpoint.description ||
                        'Avoid reprocessing identical documents'}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Configuration Summary */}
            <div className="bg-white/50 dark:bg-slate/50 p-4 rounded-lg border border-mist/50 dark:border-pewter/50">
              <h4 className="text-sm font-medium text-charcoal dark:text-white mb-2">
                Configuration Summary
              </h4>
              <div className="text-xs text-slate dark:text-mist space-y-1">
                <p>
                  • Processing up to <strong>{advancedConfig.article_limit}</strong> articles
                </p>
                <p>
                  • Events with relevance ≥{' '}
                  <strong>{advancedConfig.timeline_relevance_threshold.toFixed(2)}</strong> will be
                  included
                </p>
                <p>
                  • Using{' '}
                  <strong>
                    {advancedConfig.search_mode === 'semantic' ? 'semantic' : 'hybrid'}
                  </strong>{' '}
                  search strategy
                </p>
                <p>
                  • Viewpoint reuse is{' '}
                  <strong>
                    {advancedConfig.reuse_composite_viewpoint ? 'enabled' : 'disabled'}
                  </strong>
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-md">
          <p className="font-bold">An Error Occurred</p>
          <p>{error}</p>
        </div>
      )}

      <div className="text-center pt-4 border-t-2 border-dashed border-mist dark:border-pewter">
        <button
          type="submit"
          disabled={isSubmitting || !topic.trim()}
          className="btn btn-primary font-bold py-3 px-12 rounded-lg shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all duration-200 disabled:bg-gray-400 disabled:shadow-none disabled:transform-none disabled:cursor-not-allowed"
        >
          {isSubmitting ? 'Initiating Research...' : 'Create Chronicle'}
        </button>
      </div>
    </form>
  );
};

export default TaskForm;
