import React from 'react';
import AssetHierarchy from '../components/AssetHierarchy';

const AssetBrowser: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Asset Browser</h1>
          <p className="text-gray-600 mt-2">
            Browse your plant assets organized by Plant → Area → Equipment → Sub-Equipment → Component
          </p>
        </div>
        
        <div className="bg-white rounded-lg shadow-lg overflow-hidden" style={{ height: 'calc(100vh - 200px)' }}>
          <AssetHierarchy />
        </div>
      </div>
    </div>
  );
};

export default AssetBrowser;
