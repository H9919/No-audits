// static/js/table-utils.js - Utility functions for enhanced tables

/**
 * Enhanced Table Configuration Presets
 */
const TABLE_PRESETS = {
    incidents: {
        title: 'Incidents Management',
        defaultColumns: ['id', 'type', 'status', 'completeness', 'created_ts', 'actions'],
        quickFilters: [
            { label: 'Open', filter: (item) => item.status !== 'complete' },
            { label: 'High Completeness', filter: (item) => item.completeness >= 80 },
            { label: 'Recent', filter: (item) => isRecentDate(item.created_ts) }
        ],
        exportFileName: 'incidents_export'
    },
    capas: {
        title: 'CAPAs Management',
        defaultColumns: ['id', 'title', 'type', 'assignee', 'due_date', 'priority', 'status', 'actions'],
        quickFilters: [
            { label: 'Overdue', filter: (item) => isOverdue(item.due_date, item.status) },
            { label: 'High Priority', filter: (item) => ['high', 'critical'].includes(item.priority) },
            { label: 'In Progress', filter: (item) => item.status === 'in_progress' }
        ],
        exportFileName: 'capas_export'
    },
    sds: {
        title: 'Safety Data Sheets',
        defaultColumns: ['id', 'product_name', 'chemical_info', 'file_name', 'created_ts', 'actions'],
        quickFilters: [
            { label: 'AI Searchable', filter: (item) => item.has_embeddings },
            { label: 'Recent', filter: (item) => isRecentDate(item.created_ts) },
            { label: 'Has Hazards', filter: (item) => item.chemical_info?.hazard_statements?.length > 0 }
        ],
        exportFileName: 'sds_export'
    },
    safety_concerns: {
        title: 'Safety Concerns',
        defaultColumns: ['id', 'title', 'type', 'location', 'priority', 'status', 'created_date', 'actions'],
        quickFilters: [
            { label: 'Open', filter: (item) => ['reported', 'investigating'].includes(item.status) },
            { label: 'High Priority', filter: (item) => item.priority === 'high' },
            { label: 'Anonymous', filter: (item) => item.anonymous }
        ],
        exportFileName: 'safety_concerns_export'
    },
    risk_assessments: {
        title: 'Risk Assessments',
        defaultColumns: ['id', 'title', 'risk_level', 'risk_score', 'created_by', 'created_date', 'actions'],
        quickFilters: [
            { label: 'High Risk', filter: (item) => ['Critical', 'High'].includes(item.risk_level) },
            { label: 'Recent', filter: (item) => isRecentDate(item.created_date) },
            { label: 'Active', filter: (item) => item.status === 'active' }
        ],
        exportFileName: 'risk_assessments_export'
    }
};

/**
 * Utility Functions
 */
function isRecentDate(timestamp, days = 30) {
    if (!timestamp) return false;
    const date = new Date(typeof timestamp === 'number' ? timestamp * 1000 : timestamp);
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    return date >= cutoff;
}

function isOverdue(dueDate, status) {
    if (!dueDate || status === 'completed') return false;
    const due = new Date(dueDate);
    const now = new Date();
    return due < now;
}

function formatFileSize(bytes) {
    if (!bytes) return 'Unknown';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}

function formatRelativeTime(timestamp) {
    const date = new Date(typeof timestamp === 'number' ? timestamp * 1000 : timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
    return `${Math.floor(diffDays / 365)} years ago`;
}

/**
 * Enhanced Table Factory Function
 */
function createEnhancedTable(tableId, data, customConfig = {}) {
    const preset = TABLE_PRESETS[tableId] || {};
    const config = {
        sortable: true,
        filterable: true,
        paginated: true,
        exportable: true,
        persistPreferences: true,
        selectable: false,
        ...preset,
        ...customConfig
    };
    
    return initTable(tableId, data, generateColumns(tableId, data), config);
}

/**
 * Dynamic Column Generation
 */
function generateColumns(tableId, data) {
    if (!data || data.length === 0) return [];
    
    const preset = TABLE_PRESETS[tableId];
    const sampleRow = data[0];
    const allKeys = Object.keys(sampleRow);
    
    // Generate columns based on data structure and presets
    const columns = allKeys.map(key => {
        const column = {
            key: key,
            label: formatColumnLabel(key),
            type: detectColumnType(key, sampleRow[key]),
            filterable: true,
            sortable: true
        };
        
        // Add custom formatting based on column type and table type
        if (column.type === 'badge') {
            column.badgeMap = getBadgeMap(key, tableId);
        }
        
        if (key === 'actions') {
            column.filterable = false;
            column.sortable = false;
            column.type = 'custom';
            column.format = (value, row) => generateActionButtons(tableId, row);
        }
        
        return column;
    });
    
    // Filter to default columns if preset exists
    if (preset?.defaultColumns) {
        return columns.filter(col => preset.defaultColumns.includes(col.key));
    }
    
    return columns;
}

function formatColumnLabel(key) {
    return key
        .replace(/_/g, ' ')
        .replace(/([A-Z])/g, ' $1')
        .replace(/^./, str => str.toUpperCase())
        .trim();
}

function detectColumnType(key, value) {
    const keyLower = key.toLowerCase();
    
    if (key === 'actions') return 'custom';
    if (keyLower.includes('date') || keyLower.includes('time')) return 'date';
    if (keyLower === 'status' || keyLower === 'priority' || keyLower === 'type') return 'badge';
    if (keyLower.includes('id') && typeof value === 'string') return 'code';
    if (keyLower.includes('percent') || keyLower.includes('completeness')) return 'progress';
    if (typeof value === 'number') return 'number';
    if (typeof value === 'boolean') return 'badge';
    
    return 'text';
}

function getBadgeMap(key, tableId) {
    const maps = {
        status: {
            'open': 'secondary',
            'in_progress': 'warning', 
            'completed': 'success',
            'complete': 'success',
            'incomplete': 'warning',
            'draft': 'secondary',
            'active': 'success',
            'inactive': 'secondary',
            'resolved': 'success',
            'investigating': 'warning',
            'reported': 'info'
        },
        priority: {
            'critical': 'danger',
            'high': 'warning',
            'medium': 'info',
            'low': 'secondary'
        },
        type: {
            'corrective': 'warning',
            'preventive': 'success',
            'injury': 'danger',
            'environmental': 'warning',
            'vehicle': 'info',
            'security': 'dark',
            'property': 'secondary',
            'near_miss': 'primary',
            'concern': 'info',
            'recognition': 'success'
        },
        risk_level: {
            'Critical': 'danger',
            'High': 'warning',
            'Medium': 'info',
            'Low': 'success',
            'Very Low': 'light'
        }
    };
    
    return maps[key.toLowerCase()] || {};
}

function generateActionButtons(tableId, row) {
    const baseButtons = `
        <div class="btn-group btn-group-sm">
            <a href="/${tableId}/${row.id}" class="btn btn-outline-primary" title="View">
                <i class="bi bi-eye"></i>
            </a>
    `;
    
    let specificButtons = '';
    
    switch (tableId) {
        case 'incidents':
            specificButtons = `
                <a href="/incidents/${row.id}/edit" class="btn btn-outline-secondary" title="Edit">
                    <i class="bi bi-pencil"></i>
                </a>
                <a href="/incidents/${row.id}/pdf" class="btn btn-outline-info" title="PDF">
                    <i class="bi bi-file-pdf"></i>
                </a>
            `;
            break;
            
        case 'capas':
            if (row.status !== 'completed') {
                specificButtons = `
                    <button class="btn btn-outline-success" onclick="quickUpdateCapa('${row.id}', 'completed')" title="Complete">
                        <i class="bi bi-check"></i>
                    </button>
                `;
            }
            break;
            
        case 'sds':
            specificButtons = `
                <a href="/sds/${row.id}/download" class="btn btn-outline-secondary" title="Download">
                    <i class="bi bi-download"></i>
                </a>
                ${row.has_embeddings ? `
                    <a href="/sds/${row.id}/chat" class="btn btn-outline-info" title="AI Chat">
                        <i class="bi bi-robot"></i>
                    </a>
                ` : ''}
            `;
            break;
            
        case 'safety_concerns':
            if (row.status !== 'resolved') {
                specificButtons = `
                    <button class="btn btn-outline-warning" onclick="updateConcernStatus('${row.id}', 'investigating')" title="Investigate">
                        <i class="bi bi-search"></i>
                    </button>
                `;
            }
            break;
    }
    
    const dropdownButtons = `
        <div class="btn-group">
            <button class="btn btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
                <i class="bi bi-three-dots"></i>
            </button>
            <ul class="dropdown-menu">
                ${generateDropdownItems(tableId, row)}
            </ul>
        </div>
    `;
    
    return baseButtons + specificButtons + dropdownButtons + '</div>';
}

function generateDropdownItems(tableId, row) {
    const commonItems = `
        <li><a class="dropdown-item" href="#" onclick="duplicateRecord('${tableId}', '${row.id}')">
            <i class="bi bi-copy"></i> Duplicate
        </a></li>
        <li><a class="dropdown-item" href="#" onclick="exportRecord('${tableId}', '${row.id}')">
            <i class="bi bi-download"></i> Export
        </a></li>
        <li><hr class="dropdown-divider"></li>
    `;
    
    let specificItems = '';
    
    switch (tableId) {
        case 'incidents':
            specificItems = `
                <li><a class="dropdown-item" href="/incidents/${row.id}/capa">
                    <i class="bi bi-arrow-repeat"></i> Create CAPA
                </a></li>
                <li><a class="dropdown-item" href="#" onclick="assignInvestigator('${row.id}')">
                    <i class="bi bi-person-gear"></i> Assign Investigator
                </a></li>
            `;
            break;
            
        case 'capas':
            specificItems = `
                <li><a class="dropdown-item" href="#" onclick="reassignCapa('${row.id}')">
                    <i class="bi bi-person-gear"></i> Reassign
                </a></li>
                <li><a class="dropdown-item" href="#" onclick="extendDueDate('${row.id}')">
                    <i class="bi bi-calendar-plus"></i> Extend Due Date
                </a></li>
            `;
            break;
            
        case 'sds':
            specificItems = `
                <li><a class="dropdown-item" href="/sds/${row.id}/label">
                    <i class="bi bi-tag"></i> Generate Label
                </a></li>
                <li><a class="dropdown-item" href="#" onclick="reprocessSDS('${row.id}')">
                    <i class="bi bi-arrow-clockwise"></i> Reprocess
                </a></li>
            `;
            break;
            
        case 'safety_concerns':
            specificItems = `
                <li><a class="dropdown-item" href="/capa/new?source=safety_concern&source_id=${row.id}">
                    <i class="bi bi-arrow-repeat"></i> Create CAPA
                </a></li>
                <li><a class="dropdown-item" href="#" onclick="escalateConcern('${row.id}')">
                    <i class="bi bi-exclamation-triangle"></i> Escalate
                </a></li>
            `;
            break;
    }
    
    const archiveItem = `
        <li><a class="dropdown-item text-warning" href="#" onclick="archiveRecord('${tableId}', '${row.id}')">
            <i class="bi bi-archive"></i> Archive
        </a></li>
    `;
    
    return commonItems + specificItems + archiveItem;
}

/**
 * Advanced Filtering Functions
 */
function setupAdvancedFiltering(tableId) {
    const table = tableInstances[tableId];
    if (!table) return;
    
    // Add date range filtering
    addDateRangeFilter(tableId);
    
    // Add multi-select filtering
    addMultiSelectFilters(tableId);
    
    // Add saved filter presets
    addFilterPresets(tableId);
}

function addDateRangeFilter(tableId) {
    const dateColumns = tableInstances[tableId].columns.filter(col => col.type === 'date');
    
    dateColumns.forEach(column => {
        const filterId = `dateRange_${column.key}`;
        const filterHtml = `
            <div class="col-md-3" id="${filterId}">
                <label class="form-label">${column.label} Range</label>
                <div class="input-group input-group-sm">
                    <input type="date" class="form-control" data-column="${column.key}" data-range="start">
                    <input type="date" class="form-control" data-column="${column.key}" data-range="end">
                </div>
            </div>
        `;
        
        const container = document.getElementById(`columnFilters-${tableId}`);
        if (container) {
            container.insertAdjacentHTML('beforeend', filterHtml);
        }
    });
}

function addMultiSelectFilters(tableId) {
    const categoricalColumns = tableInstances[tableId].columns.filter(col => 
        ['badge', 'select'].includes(col.type)
    );
    
    categoricalColumns.forEach(column => {
        const uniqueValues = [...new Set(
            tableInstances[tableId].data.map(item => item[column.key]).filter(Boolean)
        )];
        
        if (uniqueValues.length > 1 && uniqueValues.length < 20) {
            createMultiSelectFilter(tableId, column, uniqueValues);
        }
    });
}

function createMultiSelectFilter(tableId, column, values) {
    const filterId = `multiSelect_${column.key}`;
    const filterHtml = `
        <div class="col-md-3" id="${filterId}">
            <label class="form-label">${column.label}</label>
            <div class="dropdown">
                <button class="btn btn-outline-secondary btn-sm dropdown-toggle w-100" type="button" data-bs-toggle="dropdown">
                    Select ${column.label}
                </button>
                <ul class="dropdown-menu" style="max-height: 200px; overflow-y: auto;">
                    ${values.map(value => `
                        <li>
                            <label class="dropdown-item">
                                <input type="checkbox" class="form-check-input me-2" 
                                       data-column="${column.key}" value="${value}">
                                ${value}
                            </label>
                        </li>
                    `).join('')}
                </ul>
            </div>
        </div>
    `;
    
    const container = document.getElementById(`columnFilters-${tableId}`);
    if (container) {
        container.insertAdjacentHTML('beforeend', filterHtml);
    }
}

/**
 * Export Functions
 */
function enhancedExport(tableId, format = 'csv') {
    const table = tableInstances[tableId];
    if (!table) return;
    
    const preset = TABLE_PRESETS[tableId];
    const filename = `${preset?.exportFileName || tableId}_${new Date().toISOString().split('T')[0]}`;
    
    switch (format) {
        case 'csv':
            exportToCSV(table, filename);
            break;
        case 'xlsx':
            exportToExcel(table, filename);
            break;
        case 'pdf':
            exportToPDF(table, filename);
            break;
        case 'json':
            exportToJSON(table, filename);
            break;
    }
}

function exportToCSV(table, filename) {
    const headers = table.visibleColumns.map(col => col.label).join(',');
    const rows = table.filteredData.map(item => 
        table.visibleColumns.map(col => {
            let value = item[col.key] || '';
            
            // Handle nested objects
            if (col.key.includes('.')) {
                const keys = col.key.split('.');
                value = keys.reduce((obj, key) => obj && obj[key], item) || '';
            }
            
            // Clean value for CSV
            if (Array.isArray(value)) {
                value = value.join('; ');
            } else if (typeof value === 'object') {
                value = JSON.stringify(value);
            }
            
            return `"${String(value).replace(/"/g, '""')}"`;
        }).join(',')
    ).join('\n');
    
    downloadFile(headers + '\n' + rows, `${filename}.csv`, 'text/csv');
}

function exportToJSON(table, filename) {
    const data = {
        exported_at: new Date().toISOString(),
        table_id: table.tableId,
        total_records: table.data.length,
        filtered_records: table.filteredData.length,
        columns: table.visibleColumns.map(col => ({
            key: col.key,
            label: col.label,
            type: col.type
        })),
        data: table.filteredData
    };
    
    downloadFile(JSON.stringify(data, null, 2), `${filename}.json`, 'application/json');
}

function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

/**
 * Bulk Operations
 */
function setupBulkOperations(tableId) {
    addSelectAllCheckbox(tableId);
    addBulkActionToolbar(tableId);
    setupRowSelection(tableId);
}

function addSelectAllCheckbox(tableId) {
    const table = tableInstances[tableId];
    if (!table) return;
    
    // Add select all checkbox to header
    const headerRow = document.getElementById(`tableHeader-${tableId}`);
    if (headerRow) {
        const selectAllTh = document.createElement('th');
        selectAllTh.innerHTML = `
            <input type="checkbox" class="form-check-input" id="selectAll-${tableId}" 
                   onchange="toggleSelectAll('${tableId}')">
        `;
        headerRow.insertBefore(selectAllTh, headerRow.firstChild);
    }
}

function addBulkActionToolbar(tableId) {
    const container = document.querySelector(`[data-table-id="${tableId}"]`);
    if (!container) return;
    
    const toolbar = document.createElement('div');
    toolbar.id = `bulkToolbar-${tableId}`;
    toolbar.className = 'alert alert-info d-none';
    toolbar.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <span id="selectedCount-${tableId}">0 items selected</span>
            <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="bulkExport('${tableId}')">
                    <i class="bi bi-download"></i> Export Selected
                </button>
                <button class="btn btn-outline-warning" onclick="bulkEdit('${tableId}')">
                    <i class="bi bi-pencil"></i> Bulk Edit
                </button>
                <button class="btn btn-outline-danger" onclick="bulkDelete('${tableId}')">
                    <i class="bi bi-trash"></i> Archive Selected
                </button>
            </div>
        </div>
    `;
    
    container.insertBefore(toolbar, container.firstChild);
}

/**
 * Real-time Updates
 */
function setupRealTimeUpdates(tableId, updateInterval = 300000) {
    setInterval(() => {
        refreshTableData(tableId);
    }, updateInterval);
}

function refreshTableData(tableId) {
    const apiEndpoint = getApiEndpoint(tableId);
    if (!apiEndpoint) return;
    
    fetch(apiEndpoint)
        .then(response => response.json())
        .then(data => {
            const table = tableInstances[tableId];
            if (table) {
                table.setData(data.items || data, table.columns);
                showUpdateNotification(tableId);
            }
        })
        .catch(error => {
            console.error(`Error refreshing ${tableId} data:`, error);
        });
}

function getApiEndpoint(tableId) {
    const endpoints = {
        'incidents': '/api/incidents',
        'capas': '/capa/api/list',
        'sds': '/api/sds',
        'safety_concerns': '/api/safety-concerns',
        'risk_assessments': '/api/risk-assessments'
    };
    
    return endpoints[tableId];
}

function showUpdateNotification(tableId) {
    const notification = document.createElement('div');
    notification.className = 'alert alert-success alert-dismissible fade show position-fixed';
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        <i class="bi bi-check-circle me-2"></i>
        ${TABLE_PRESETS[tableId]?.title || 'Table'} data updated
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

/**
 * Accessibility Enhancements
 */
function enhanceAccessibility(tableId) {
    const table = document.getElementById(`dataTable-${tableId}`);
    if (!table) return;
    
    // Add ARIA labels
    table.setAttribute('role', 'table');
    table.setAttribute('aria-label', `${TABLE_PRESETS[tableId]?.title || 'Data'} table`);
    
    // Add keyboard navigation
    addKeyboardNavigation(tableId);
    
    // Add screen reader announcements
    addScreenReaderSupport(tableId);
}

function addKeyboardNavigation(tableId) {
    const table = document.getElementById(`dataTable-${tableId}`);
    
    table.addEventListener('keydown', (e) => {
        const focused = document.activeElement;
        
        if (e.key === 'ArrowRight') {
            const nextCell = focused.nextElementSibling;
            if (nextCell) nextCell.focus();
        } else if (e.key === 'ArrowLeft') {
            const prevCell = focused.previousElementSibling;
            if (prevCell) prevCell.focus();
        } else if (e.key === 'ArrowDown') {
            const currentRow = focused.closest('tr');
            const nextRow = currentRow?.nextElementSibling;
            if (nextRow) {
                const cellIndex = Array.from(currentRow.children).indexOf(focused.closest('td'));
                nextRow.children[cellIndex]?.focus();
            }
        } else if (e.key === 'ArrowUp') {
            const currentRow = focused.closest('tr');
            const prevRow = currentRow?.previousElementSibling;
            if (prevRow) {
                const cellIndex = Array.from(currentRow.children).indexOf(focused.closest('td'));
                prevRow.children[cellIndex]?.focus();
            }
        }
    });
}

// Global initialization function
function initializeEnhancedTables() {
    // Add CSS for enhanced tables if not already present
    if (!document.getElementById('enhanced-table-styles')) {
        const styles = document.createElement('style');
        styles.id = 'enhanced-table-styles';
        styles.textContent = `
            .table-container { position: relative; }
            .table-loading { 
                position: absolute; 
                top: 50%; 
                left: 50%; 
                transform: translate(-50%, -50%); 
                z-index: 10; 
            }
            .table-overlay { 
                position: absolute; 
                top: 0; 
                left: 0; 
                right: 0; 
                bottom: 0; 
                background: rgba(255,255,255,0.8); 
                z-index: 9; 
            }
            .bulk-toolbar { 
                position: sticky; 
                top: 0; 
                z-index: 5; 
                background: white; 
                border-bottom: 1px solid #dee2e6; 
            }
            .filter-badge { 
                font-size: 0.75rem; 
                margin-right: 0.25rem; 
            }
        `;
        document.head.appendChild(styles);
    }
}

// Initialize when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeEnhancedTables);
} else {
    initializeEnhancedTables();
}
