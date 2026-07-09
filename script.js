let map;
let drawingManager;
let drawnBoundary = [];
let drawnRoads = [];
let activeResults = [];
let userDrawnShapes = [];
let currentUser = null;
let lastOptimizationResult = null;
let userHistory = [];
let isCurrentRunSaved = false;
let millMarker = null;
// Holds a user-chosen entrance gate for the entrance-sensitivity study.
// null = let the backend auto-pick the gate nearest the mill (default).
let chosenEntrance = null;

// --- AUTHENTICATION LOGIC ---
function toggleAuthMode() {
    document.getElementById('auth-inner').classList.toggle('is-flipped');
}

async function registerUser(e) {
    e.preventDefault();
    const u = document.getElementById('reg-username').value;
    const p = document.getElementById('reg-password').value;
    fetchHistory();
    
    try {
        const response = await fetch('http://127.0.0.1:8000/register', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: u, password: p})
        });
        const data = await response.json();
        
        if(data.error) {
            alert(data.error);
        } else {
            currentUser = u;
            document.getElementById('current-username').innerText = currentUser;
            document.getElementById('auth-overlay').classList.add('hidden');
            fetchHistory(); 
        }
    } catch (err) {
        alert("Server error. Is the Python backend running?");
    }
}

async function loginUser(e) {
    e.preventDefault();
    const u = document.getElementById('login-username').value;
    const p = document.getElementById('login-password').value;
    fetchHistory();
    
    try {
        const response = await fetch('http://127.0.0.1:8000/login', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: u, password: p})
        });
        const data = await response.json();
        
        if(data.error) {
            alert(data.error);
        } else {
            currentUser = data.username;
            document.getElementById('current-username').innerText = currentUser;
            document.getElementById('auth-overlay').classList.add('hidden');
            fetchHistory(); 
        }
    } catch (err) {
        alert("Server error. Is the Python backend running?");
    }
}

function logoutUser() {
    userDrawnShapes.forEach(shape => shape.setMap(null));
    userDrawnShapes = [];
    activeResults.forEach(item => item.setMap(null));
    activeResults = [];
    drawnBoundary = [];
    drawnRoads = [];
    
    currentUser = null;
    userHistory = [];
    document.getElementById('current-username').innerText = "Guest";
    document.getElementById('history-container').innerHTML = '<p class="text-xs text-gray-400 italic">Please log in to view history.</p>';
    document.getElementById('auth-overlay').classList.remove('hidden');
}

// --- DATABASE HISTORY LOGIC ---
async function fetchHistory() {
    if(!currentUser) return;
    try {
        const res = await fetch(`http://127.0.0.1:8000/history/${currentUser}`);
        const data = await res.json();
        if(data.status === "success") {
            userHistory = data.history;
            renderHistoryList();
        }
    } catch(e) {
        console.error("Failed to load history");
    }
}

function renderHistoryList() {
    const container = document.getElementById('history-container'); 
    container.innerHTML = ''; 
    if(userHistory.length === 0) {
        container.innerHTML = '<p class="text-xs text-gray-400 italic">No saved routes yet.</p>';
        return;
    }

    userHistory.forEach((record, index) => {
        const div = document.createElement('div');
        div.className = "bg-white p-3 rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition relative group";
        
        let displayName = record.custom_name || `Optimization ${userHistory.length - index}`;
        
        div.innerHTML = `
            <div class="flex justify-between items-center cursor-pointer" onclick="loadSavedRoute(${index})">
                <p class="font-bold text-sm text-gray-800 truncate pr-2">${displayName}</p>
                <span class="text-[10px] text-gray-400">${record.date_saved.split(',')[0]}</span>
            </div>
            <div class="mt-2 flex items-center justify-between">
                <span class="bg-gray-600 text-white text-[10px] px-2 py-1 rounded-full">${record.metrics.distance_km} km</span>
                <div class="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onclick="renameHistory('${record._id}', '${displayName}')" class="text-blue-500 hover:text-blue-700"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg></button>
                    <button onclick="deleteHistory('${record._id}')" class="text-red-500 hover:text-red-700"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg></button>
                </div>
            </div>
        `;
        container.appendChild(div);
    });
}

async function deleteHistory(id) {
    if(!confirm("Delete this saved route?")) return;
    await fetch(`http://127.0.0.1:8000/history/${id}`, { method: 'DELETE' });
    fetchHistory(); 
}

async function renameHistory(id, oldName) {
    const newName = prompt("Enter new name for this route:", oldName);
    if(!newName || newName === oldName) return;
    await fetch(`http://127.0.0.1:8000/history/${id}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: newName})
    });
    fetchHistory(); 
}

function loadSavedRoute(index) {
    const record = userHistory[index];
    document.getElementById('action-buttons').classList.add('hidden');

    // Restore the saved mill BEFORE displayResults so the macro-route
    // (mill -> estate entrance) is drawn again just like on the original run.
    if (millMarker) { millMarker.setMap(null); millMarker = null; }
    if (record.mill && record.mill.position) {
        millMarker = new google.maps.Marker({
            position: { lat: record.mill.position[0], lng: record.mill.position[1] },
            map: map,
            title: record.mill.name || "Saved Mill"
        });
        document.getElementById('location-name').innerText = "Mill: " + (record.mill.name || "Saved Mill");
    }

    displayResults(record.full_data);
    
    drawnBoundary = record.boundary;
    drawnRoads = record.roads;
    lastOptimizationResult = record.full_data;
    
    const restoredPoly = new google.maps.Polygon({
        paths: drawnBoundary.map(pt => ({lat: pt[0], lng: pt[1]})),
        fillColor: "#00FF00", fillOpacity: 0.2, strokeWeight: 3, strokeColor: "#00FF00", clickable: false, map: map
    });
    activeResults.push(restoredPoly); 

    // Only draw raw roads if the result doesn't already carry processed_roads
    // (displayResults handles the road layer when processed_roads is present)
    if (!record.full_data.processed_roads) {
        drawnRoads.forEach(road => {
            const restoredLine = new google.maps.Polyline({
                path: road.map(pt => ({lat: pt[0], lng: pt[1]})),
                strokeColor: "#ffffff", strokeWeight: 4, clickable: false, map: map, zIndex: 2
            });
            activeResults.push(restoredLine);
        });
    }

    const bounds = new google.maps.LatLngBounds();
    drawnBoundary.forEach(pt => bounds.extend({lat: pt[0], lng: pt[1]}));
    map.fitBounds(bounds);
}

async function saveAnalysisToDB() {
    if (!currentUser) return alert("You must be logged in to save data.");
    if (!lastOptimizationResult) return alert("No route data found to save!");
    if (isCurrentRunSaved) return alert("This specific optimization has already been saved!");

    // Include the mill so a reloaded route restores the exact same setup.
    let millData = null;
    if (millMarker) {
        millData = {
            position: [millMarker.getPosition().lat(), millMarker.getPosition().lng()],
            name: millMarker.getTitle() || "Saved Mill"
        };
    }

    const payload = {
        username: currentUser,
        date_saved: new Date().toLocaleString(),
        metrics: lastOptimizationResult.metrics,
        boundary: drawnBoundary, 
        roads: drawnRoads,       
        mill: millData,
        full_data: lastOptimizationResult 
    };

    try {
        const response = await fetch('http://127.0.0.1:8000/save_analysis', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        isCurrentRunSaved = true; 
        alert(data.message || "Route saved to Database successfully!");
        fetchHistory(); 
    } catch(err) {
        alert("Failed to save to database.");
    }
}

// --- APP UI LOGIC ---
function startTutorial() {
    const driver = window.driver.js.driver;
    const driverObj = driver({
        showProgress: true,
        steps: [
            { element: '#search-box', popover: { title: '1. Find Location', description: 'Search for your plantation area (e.g., Terengganu) to fly the map there.', side: "bottom" }},
            { element: '#new-route-btn', popover: { title: '2. Initialize Setup', description: 'Click here to clear the map and open the Route Setup panel.', side: "right" }},
            { element: '#btn-draw-boundary', popover: { title: '3. Define Estate', description: 'Click the map to outline your plantation. This green polygon determines your total hectare area and estimated tonnage.', side: "right" }},
            { element: '#btn-draw-roads', popover: { title: '4. Map Dirt Roads', description: 'Draw white lines to represent the navigable dirt roads inside your estate. Double-click to finish a road segment.', side: "right" }},
            { element: '#control-menu', popover: { title: '5. Macro-Routing & Execution', description: 'Auto-detect the nearest processing mill on public highways, then run the optimization AI.', side: "top" }}
        ]
    });
    driverObj.drive();
}

function autoDetectNearestMill() {
    if (drawnBoundary.length === 0) {
        return alert("Please draw your estate boundary first so we know where to search from!");
    }

    const bounds = new google.maps.LatLngBounds();
    drawnBoundary.forEach(pt => bounds.extend({lat: pt[0], lng: pt[1]}));
    const estateCenter = bounds.getCenter();

    document.getElementById('location-name').innerText = "Scanning for nearest mill...";

    const service = new google.maps.places.PlacesService(map);

    // Palm-oil mills are labelled in the local language, so a Malay-only
    // keyword ("kilang sawit") finds nothing outside Malaysia. Search a
    // multilingual set of terms (English + Spanish + Malay/Indonesian) so the
    // tool works in other producing regions such as Colombia, where mills are
    // "extractora de aceite de palma" / "planta extractora". If that still
    // returns nothing, retry once with the plain English term before giving up.
    const primaryKeyword =
        'palm oil mill OR extractora de aceite de palma OR planta extractora ' +
        'OR kilang sawit OR pabrik kelapa sawit';
    const fallbackKeyword = 'palm oil mill';

    const handle = (bounds) => (results, status) => {
        if (status === google.maps.places.PlacesServiceStatus.OK && results.length > 0) {
            const closestMill = results[0];
            if (millMarker) millMarker.setMap(null);
            millMarker = new google.maps.Marker({
                position: closestMill.geometry.location,
                map: map,
                title: closestMill.name,
                animation: google.maps.Animation.DROP
            });
            alert(`Nearest mill detected: ${closestMill.name}\nLocation set automatically!`);
            document.getElementById('location-name').innerText = "Mill: " + closestMill.name;
            bounds.extend(closestMill.geometry.location);
            map.fitBounds(bounds);
            return true;
        }
        return false;
    };

    const request = {
        location: estateCenter,
        rankBy: google.maps.places.RankBy.DISTANCE, // Strict distance, ignore popularity
        keyword: primaryKeyword
    };

    service.nearbySearch(request, (results, status) => {
        if (handle(bounds)(results, status)) return;
        // Fallback: retry once with the generic English term.
        service.nearbySearch(
            { location: estateCenter, rankBy: google.maps.places.RankBy.DISTANCE, keyword: fallbackKeyword },
            (r2, s2) => {
                if (handle(bounds)(r2, s2)) return;
                alert("Could not automatically find a palm oil mill nearby. Please set it manually by clicking on the map.");
                document.getElementById('location-name').innerText = "Detection Failed";
            }
        );
    });
}

// Manual mill placement. Google disabled PlacesService (nearbySearch) for
// new API projects from March 2025, so auto-detect can fail entirely. This
// lets the user click the map to drop the mill pin themselves -- independent
// of the Places API and of the drawing tools. Call enableManualMillMode()
// (e.g. from a "Set Mill Manually" button); the next map click sets the mill.
let manualMillListener = null;

function enableManualMillMode() {
    document.getElementById('location-name').innerText =
        "Click on the map to place the mill...";
    // Remove any previous pending listener so clicks don't stack up.
    if (manualMillListener) {
        google.maps.event.removeListener(manualMillListener);
        manualMillListener = null;
    }
    manualMillListener = map.addListener('click', (event) => {
        const lat = event.latLng.lat();
        const lng = event.latLng.lng();
        if (millMarker) millMarker.setMap(null);
        millMarker = new google.maps.Marker({
            position: { lat: lat, lng: lng },
            map: map,
            title: "Mill (manually placed)",
            animation: google.maps.Animation.DROP
        });
        document.getElementById('location-name').innerText =
            `Mill set manually at ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
        // One-shot: stop listening after the pin is placed.
        google.maps.event.removeListener(manualMillListener);
        manualMillListener = null;
    });
}

function createNewRoute() {
    userDrawnShapes.forEach(shape => shape.setMap(null));
    userDrawnShapes = [];
    activeResults.forEach(item => item.setMap(null));
    activeResults = [];
    drawnBoundary = [];
    drawnRoads = [];
    lastOptimizationResult = null;
    isCurrentRunSaved = false;

    document.getElementById('analytics-panel').classList.add('translate-x-[120%]');
    const controlMenu = document.getElementById('control-menu');
    controlMenu.classList.remove('hidden', 'opacity-0', 'pointer-events-none');
    
    // Reveal the new setup panel
    const setupPanel = document.getElementById('setup-panel');
    if (setupPanel) {
        setupPanel.classList.remove('hidden');
        setupPanel.classList.add('flex');
    }
}

function closeAnalytics() {
    document.getElementById('analytics-panel').classList.add('translate-x-[120%]');
    activeResults.forEach(item => item.setMap(null));
    activeResults = [];
    lastOptimizationResult = null;
    isCurrentRunSaved = false;
    document.getElementById('control-menu').classList.remove('opacity-0', 'pointer-events-none', 'hidden');
    // Restore original drawn road polylines that were hidden during results display
    userDrawnShapes.forEach(shape => shape.setMap(map));
}

function adjustAndRerun() {
    closeAnalytics();
    activeResults.forEach(item => item.setMap(null));
    activeResults = [];
}

// --- CUSTOM DRAWING CONTROLS ---
function setDrawMode(type) {
    const btnBoundary = document.getElementById('btn-draw-boundary');
    const btnRoad = document.getElementById('btn-draw-roads');

    const activeClass = ['bg-green-50', 'text-green-700', 'border-green-200'];
    const inactiveClass = ['bg-gray-50', 'text-gray-700', 'border-gray-200'];

    if (btnBoundary && btnRoad) {
        btnBoundary.classList.remove(...activeClass);
        btnBoundary.classList.add(...inactiveClass);
        btnRoad.classList.remove(...activeClass);
        btnRoad.classList.add(...inactiveClass);
    }

    if (type === 'boundary') {
        drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYGON);
        if (btnBoundary) {
            btnBoundary.classList.remove(...inactiveClass);
            btnBoundary.classList.add(...activeClass);
        }
    } else if (type === 'road') {
        drawingManager.setDrawingMode(google.maps.drawing.OverlayType.POLYLINE);
        if (btnRoad) {
            btnRoad.classList.remove(...inactiveClass);
            btnRoad.classList.add(...activeClass);
        }
    } else {
        drawingManager.setDrawingMode(null); 
    }
}

// --- GOOGLE MAPS LOGIC ---
function initMap() {
    const centerPt = { lat: 3.0738, lng: 101.5183 };
    const geocoder = new google.maps.Geocoder();

    function updateLocationPill(latLng) {
        document.getElementById('location-name').innerText = "Detecting...";
        geocoder.geocode({ location: latLng }, (results, status) => {
            if (status === "OK" && results[0]) {
                let cityResult = results.find(r => r.types.includes('locality') || r.types.includes('administrative_area_level_2'));
                let displayName = cityResult ? cityResult.formatted_address : results[0].formatted_address;
                document.getElementById('location-name').innerText = "Showing: " + displayName;
            } else {
                document.getElementById('location-name').innerText = "Showing: Unknown Location";
            }
        });
    }

    map = new google.maps.Map(document.getElementById("map"), {
        zoom: 16, center: centerPt, mapTypeId: 'satellite', 
        disableDefaultUI: true, zoomControl: true
    });

    updateLocationPill(centerPt);
    map.addListener("idle", () => updateLocationPill(map.getCenter()));

    drawingManager = new google.maps.drawing.DrawingManager({
        drawingMode: null, 
        drawingControl: false, // Hidden! Handled by custom buttons now
        polygonOptions: { fillColor: "#00FF00", fillOpacity: 0.2, strokeWeight: 3, strokeColor: "#00FF00", clickable: false, editable: true, zIndex: 1 },
        polylineOptions: { strokeColor: "#ffffff", strokeWeight: 4, clickable: false, editable: false, zIndex: 2 }
    });
    drawingManager.setMap(map);

    const input = document.getElementById("search-box");
    const searchBox = new google.maps.places.SearchBox(input);
    map.addListener("bounds_changed", () => searchBox.setBounds(map.getBounds()));

    searchBox.addListener("places_changed", () => {
        const places = searchBox.getPlaces();
        if (places.length == 0) return;
        const bounds = new google.maps.LatLngBounds();
        places.forEach((place) => {
            if (!place.geometry || !place.geometry.location) return;
            if (place.geometry.viewport) bounds.union(place.geometry.viewport);
            else bounds.extend(place.geometry.location);
        });
        map.fitBounds(bounds);
        map.setZoom(16); 
        document.getElementById('location-name').innerText = "Showing: " + places[0].name;
    });

    // Snap Indicator (Node Snapping to avoid Overpass Problem)
    const snapIndicator = new google.maps.Circle({
        strokeColor: "#FFFFFF", strokeOpacity: 1, strokeWeight: 3, 
        fillColor: "#FFD700", fillOpacity: 0.9, 
        map: map, radius: 8, visible: false, zIndex: 100
    });

    map.addListener("mousemove", function(e) {
        if (drawingManager.getDrawingMode() !== google.maps.drawing.OverlayType.POLYLINE) {
            snapIndicator.setVisible(false); return;
        }
        
        const mouseLat = e.latLng.lat();
        const mouseLng = e.latLng.lng();
        let closestPt = null;
        let minDist = 0.00015;

        drawnRoads.forEach(road => {
            road.forEach(pt => {
                let dist = Math.hypot(pt[0] - mouseLat, pt[1] - mouseLng);
                if (dist < minDist) {
                    minDist = dist;
                    closestPt = pt;
                }
            });
        });

        if (closestPt) {
            snapIndicator.setCenter({ lat: closestPt[0], lng: closestPt[1] });
            snapIndicator.setVisible(true);
        } else { 
            snapIndicator.setVisible(false); 
        }
    });

    google.maps.event.addListener(drawingManager, 'overlaycomplete', function(event) {
        userDrawnShapes.push(event.overlay);
        
        if (event.type === 'polygon') {
            drawnBoundary = [];
            const path = event.overlay.getPath();
            for (let i = 0; i < path.getLength(); i++) drawnBoundary.push([path.getAt(i).lat(), path.getAt(i).lng()]);
            
            setDrawMode('road'); // Revert back to instantly switching to manual road drawing
        }
        else if (event.type === 'polyline') {
            let roadSegment = [];
            const path = event.overlay.getPath();
            
            for (let i = 0; i < path.getLength(); i++) {
                let lat = path.getAt(i).lat(); 
                let lng = path.getAt(i).lng();
                let minDist = 0.00015;
                let snapped = false;

                drawnRoads.forEach(road => {
                    road.forEach(pt => {
                        let dist = Math.hypot(pt[0] - lat, pt[1] - lng);
                        if (dist < minDist) { 
                            minDist = dist; 
                            lat = pt[0]; 
                            lng = pt[1]; 
                            snapped = true; 
                        }
                    });
                });
                
                if (snapped) path.setAt(i, new google.maps.LatLng(lat, lng));
                roadSegment.push([lat, lng]);

                // Render the visible blue node
                let visualNode = new google.maps.Circle({
                    strokeColor: "#FFFFFF", strokeOpacity: 0.9, strokeWeight: 1,
                    fillColor: "#3B82F6", fillOpacity: 1,
                    map: map, center: { lat: lat, lng: lng },
                    radius: 3,
                    zIndex: 10
                });
                userDrawnShapes.push(visualNode); 
            }
            drawnRoads.push(roadSegment);
        }
    });
}

// --- TRIGGER PYTHON BACKEND ---
async function runOptimization() {
    if (drawnBoundary.length < 3 || drawnRoads.length === 0) {
        alert("Please draw a green boundary polygon AND at least one white road line first.");
        return;
    }

    const k = parseInt(document.getElementById('fcp-count').value);
    
    const loader = document.getElementById('loading-overlay');
    const loadText = document.getElementById('loading-text');
    loader.classList.remove('hidden');
    loadText.innerText = "Clustering Fruit Data...";
    
    setTimeout(() => loadText.innerText = "Running Dijkstra's Pathfinding...", 1000);
    setTimeout(() => loadText.innerText = "Executing Genetic Algorithm...", 2000);
    setTimeout(() => loadText.innerText = "Calculating Lorry Constraints...", 3000);

    // Grab the Mill coordinates if the user clicked Auto-Detect
    let millCoords = null;
    if (typeof millMarker !== 'undefined' && millMarker !== null) {
        millCoords = [millMarker.getPosition().lat(), millMarker.getPosition().lng()];
    }

    const payload = { 
        boundary: drawnBoundary, 
        roads: drawnRoads, 
        num_fcps: k,
        mill: millCoords, // Sending mill to backend
        entrance_override: chosenEntrance // null = auto-pick; set = forced gate
    };

    try {
        const response = await fetch('http://127.0.0.1:8000/optimize', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        const result = await response.json();
        
        if (result.error) { 
            alert("Error from server: " + result.error); 
            loader.classList.add('hidden'); 
        } 
        else { 
            loader.classList.add('hidden');
            lastOptimizationResult = result;
            isCurrentRunSaved = false;
            document.getElementById('action-buttons').classList.remove('hidden');
            
            // Note: The alert() has been removed here. It's now beautifully handled in displayResults() UI!
            displayResults(result); 
        }
    } catch (error) {
        console.error(error);
        alert("Could not connect to the Python server.");
        loader.classList.add('hidden');
    }
}

// --- RENDER RESULTS & UI ---
function displayResults(data) {
    activeResults.forEach(item => item.setMap(null));
    activeResults = [];

    // Replace original drawn roads with the backend-processed road network so
    // that the white lines and the yellow route follow the exact same coordinates.
    if (data.processed_roads) {
        userDrawnShapes.forEach(shape => {
            if (shape instanceof google.maps.Polyline) shape.setMap(null);
        });
        data.processed_roads.forEach(road => {
            let line = new google.maps.Polyline({
                path: road.map(pt => ({lat: pt[0], lng: pt[1]})),
                strokeColor: "#ffffff", strokeWeight: 2, clickable: false, map: map, zIndex: 15
            });
            line._isProcessedRoad = true;
            activeResults.push(line);
        });
    }

    const segmentContainer = document.getElementById('segment-breakdown');
    segmentContainer.innerHTML = ''; 
    
    data.segments.forEach((seg, index) => {
        let label = seg.label ? seg.label : `Segment ${index + 1}`;
        let row = `
        <div class="flex justify-between px-4 py-3 border-b border-gray-100 text-sm hover:bg-gray-50 transition-colors">
            <span class="text-gray-600 font-medium">${label}</span>
            <span class="font-bold text-gray-800">${seg.distance_km} km</span>
        </div>`;
        segmentContainer.innerHTML += row;
    });

    const panel = document.getElementById('analytics-panel');
    panel.classList.remove('hidden', 'translate-x-[120%]');
    document.getElementById('control-menu').classList.add('opacity-0', 'pointer-events-none');
    
    // --- 1. HARVESTER ERGONOMIC UI UPDATE ---
    const fcpBox = document.getElementById('fcp-warning-box');
    if (data.metrics && data.metrics.actual_max_walk_m > 150) {
        fcpBox.classList.remove('hidden');
        fcpBox.classList.add('flex');
        document.getElementById('fcp-warning-text').innerText = `You requested ${data.fcps.length} FCPs, forcing harvesters to walk up to ${data.metrics.actual_max_walk_m}m. The safe maximum limit is 50m.`;
        document.getElementById('fcp-suggested-text').innerText = `Recommended PALM-OPT Layout: ${data.metrics.recommended_fcps} FCPs`;
    } else {
        fcpBox.classList.add('hidden');
        fcpBox.classList.remove('flex');
    }
    
    // --- 2. CALCULATE INTERNAL VS TOTAL DISTANCE ---
    let internalDistKm = data.metrics.distance_km;
    let internalTimeMin = data.metrics.time_mins;
    
    const macroSegment = data.segments.find(s => s.label === "Estate Exit to Mill");
    if (macroSegment) {
        internalDistKm -= (macroSegment.distance_km * 2);
        internalTimeMin -= ((macroSegment.distance_km * 2) / 20.0) * 60; // Python used 20km/h
    }

    // Set internal metrics instantly
    document.getElementById('res-dist-internal').innerText = "Internal: " + internalDistKm.toFixed(2) + " km";
    document.getElementById('res-time-internal').innerText = "Internal: " + internalTimeMin.toFixed(1) + " min";
    
    // Default Total (Will be overwritten by Google API if Mill is selected)
    document.getElementById('res-dist').innerText = internalDistKm.toFixed(2) + " km";
    document.getElementById('res-time').innerText = internalTimeMin.toFixed(1) + " min";

    // --- 3. AREA AND YIELD CALCULATION ---
    let hectares = 0;
    let totalTonnes = 0;
    try {
        const polygonPath = data.boundary ? data.boundary.map(pt => new google.maps.LatLng(pt[0], pt[1])) : drawnBoundary.map(pt => new google.maps.LatLng(pt[0], pt[1]));
        const areaSqMeters = google.maps.geometry.spherical.computeArea(polygonPath);
        hectares = (areaSqMeters / 10000).toFixed(2);
        totalTonnes = (hectares * 1.5).toFixed(1);
        
        const areaElement = document.getElementById('res-area');
        const yieldElement = document.getElementById('res-weight-top');
        
        if (areaElement) areaElement.innerText = hectares + " Ha";
        if (yieldElement) yieldElement.innerText = totalTonnes + " Tonnes";
        
    } catch (error) {
        console.error("Geometry calculation failed. Ensure 'geometry' is in the Google Maps API URL.", error);
    }
    
    // --- 4. VEHICLE METRICS ---
    let suggestedLorry = "";
    if (totalTonnes <= 3.0) {
        suggestedLorry = "1x 4WD Pickup / Mini-Tractor (<3T)";
    } else if (totalTonnes <= 10.0) {
        suggestedLorry = "1x 6-Wheeler Rigid Lorry (10T Limit)";
    } else if (totalTonnes <= 20.0) {
        suggestedLorry = "1x 10-Wheeler Heavy Lorry (20T Limit)";
    } else {
        suggestedLorry = Math.ceil(totalTonnes / 20) + "x 20-Ton Trailers / Bin Systems";
    }

    document.getElementById('res-weight').innerText = totalTonnes + " Tonnes Est. Yield";
    document.getElementById('res-lorry').innerText = suggestedLorry;

    // --- 5b. FCP COUNT AND MAX WALKING DISTANCE ---
    if (document.getElementById('res-fcp-count')) {
        document.getElementById('res-fcp-count').innerText = data.fcps.length;
    }
    if (document.getElementById('res-max-walk') && data.metrics && data.metrics.actual_max_walk_m !== undefined) {
        document.getElementById('res-max-walk').innerText = Math.round(data.metrics.actual_max_walk_m) + " m";
    }

    // --- 5. RENDER SHAPES AND SEQUENCE ---
    data.fruits.forEach(f => {
        let circle = new google.maps.Circle({
            strokeColor: "#00FF00", strokeOpacity: 0.8, strokeWeight: 2,
            fillColor: "#00FF00", fillOpacity: 1, map: map, center: {lat: f[0], lng: f[1]}, radius: 2
        });
        activeResults.push(circle);
    });

    data.fcps.forEach((fcp, index) => {
        let sequenceNumber = data.sequence.indexOf(index) + 1;
        let marker = new google.maps.Marker({
            position: {lat: fcp[0], lng: fcp[1]}, map: map,
            label: { text: sequenceNumber.toString(), color: "white", fontWeight: "bold" },
            icon: { path: google.maps.SymbolPath.CIRCLE, scale: 12, fillColor: "#B91C1C", fillOpacity: 1, strokeColor: "white", strokeWeight: 2 }
        });
        activeResults.push(marker);
    });

    if (data.estate_entrance) {
        let entranceMarker = new google.maps.Marker({
            position: {lat: data.estate_entrance[0], lng: data.estate_entrance[1]},
            map: map,
            title: "Estate Entrance (click to reset to automatic gate)",
            label: { text: "E", color: "white", fontWeight: "bold" },
            icon: {
                path: google.maps.SymbolPath.CIRCLE, scale: 11,
                fillColor: "#2563EB", fillOpacity: 1, strokeColor: "white", strokeWeight: 2
            },
            zIndex: 20
        });
        entranceMarker.addListener("click", () => {
            if (chosenEntrance !== null) {
                chosenEntrance = null;           // back to automatic
                runOptimization();
            }
        });
        activeResults.push(entranceMarker);
    }

    if (data.gate_candidates && data.gate_candidates.length > 1) {
        const ent = data.estate_entrance;
        const near = (a, b) => a && b &&
            Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;
        data.gate_candidates.forEach(gate => {
            if (near(gate, ent)) return;         // that one is the "E" marker
            let gateMarker = new google.maps.Marker({
                position: {lat: gate[0], lng: gate[1]},
                map: map,
                title: "Alternative gate (click to use as entrance)",
                label: { text: "G", color: "white", fontWeight: "bold" },
                icon: {
                    path: google.maps.SymbolPath.CIRCLE, scale: 9,
                    fillColor: "#6B7280", fillOpacity: 0.95, strokeColor: "white", strokeWeight: 2
                },
                zIndex: 15
            });
            gateMarker.addListener("click", () => {
                chosenEntrance = [gate[0], gate[1]];
                runOptimization();               // re-run anchored at this gate
            });
            activeResults.push(gateMarker);
        });
    }

    const lineSymbol = {
        path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
        scale: 3, strokeColor: "#ffffff", fillColor: "#FBBF24", fillOpacity: 1, strokeWeight: 2
    };

    const routeCoords = data.path.map(pt => ({lat: pt[0], lng: pt[1]}));
    let routeLine = new google.maps.Polyline({
        path: routeCoords, 
        geodesic: true, 
        strokeColor: "#FBBF24", 
        strokeOpacity: 0.9, 
        strokeWeight: 6, 
        map: map, 
        zIndex: 10
        // The icons array has been removed to stop the stacking arrows
    });
    activeResults.push(routeLine);

    // --- 6. VISUALIZE THE MACRO-ROUTE (MILL TO ESTATE VIA PUBLIC HIGHWAY) ---
    if (millMarker && (data.gate_candidates || data.estate_entrance)) {
        const millPos = new google.maps.LatLng(millMarker.getPosition().lat(), millMarker.getPosition().lng());

        // Fall back to the single provisional entrance if no candidates.
        const candidates = (data.gate_candidates && data.gate_candidates.length)
            ? data.gate_candidates
            : [data.estate_entrance];

        const directionsService = new google.maps.DirectionsService();

        // Wrap one Directions request in a Promise so we can race all gates.
        const routeToGate = (gate) => new Promise((resolve) => {
            const dest = new google.maps.LatLng(gate[0], gate[1]);
            directionsService.route({
                origin: millPos,
                destination: dest,
                travelMode: google.maps.TravelMode.DRIVING
            }, (response, status) => {
                if (status === 'OK') {
                    resolve({
                        gate: gate,
                        distKm: response.routes[0].legs[0].distance.value / 1000,
                        timeMin: response.routes[0].legs[0].duration.value / 60,
                        path: response.routes[0].overview_path
                    });
                } else {
                    resolve(null); // unreachable / API miss -- drop this gate
                }
            });
        });

        Promise.all(candidates.map(routeToGate)).then((results) => {
            const valid = results.filter(r => r !== null);

            if (valid.length === 0) {
                // Total API failure: straight-line fallback to provisional entrance.
                const fb = data.estate_entrance;
                if (fb) {
                    const line = new google.maps.Polyline({
                        path: [millPos, new google.maps.LatLng(fb[0], fb[1])],
                        strokeColor: "#3B82F6", strokeOpacity: 0.7, strokeWeight: 4, map: map
                    });
                    activeResults.push(line);
                }
                return;
            }

            // Pick the gate with the shortest REAL road distance.
            const best = valid.reduce((a, b) => (b.distKm < a.distKm ? b : a));

            const macroRouteLine = new google.maps.Polyline({
                path: best.path,
                strokeColor: "#3B82F6", strokeOpacity: 0.9, strokeWeight: 6, map: map, zIndex: 5
            });
            activeResults.push(macroRouteLine);

            const googleDistKm = best.distKm;
            const googleTimeMin = best.timeMin;

            const exactTotalKm = (internalDistKm + (googleDistKm * 2)).toFixed(2);
            const exactTotalTime = (internalTimeMin + (googleTimeMin * 2)).toFixed(1);

            document.getElementById('res-dist').innerText = exactTotalKm + " km";
            document.getElementById('res-time').innerText = exactTotalTime + " min";

            const segContainer = document.getElementById('segment-breakdown');
            const segmentDivs = segContainer.getElementsByTagName('div');

            // Update the closing macro leg (the last row, "Estate Exit to
            // Mill") to the live figure. This does NOT touch the internal
            // legs.
            if (segmentDivs.length > 0) {
                segmentDivs[segmentDivs.length - 1].innerHTML =
                    `<span class="text-gray-600 font-medium">Estate Exit to Mill (Live API)</span>` +
                    `<span class="font-bold text-blue-600">${googleDistKm.toFixed(2)} km</span>`;
            }

            // Prepend the inbound macro leg (Mill -> Entrance) as its OWN
            // row. Previously this overwrote row 0, which happened to be
            // "Entrance to FCP 1" -- silently deleting the harvester's first
            // internal leg. Prepending preserves the full breakdown:
            //   Mill -> Entrance | Entrance -> FCP1 | FCP1 -> FCP2 | ... |
            //   FCP N -> Entrance | Estate Exit -> Mill
            const existingMillIn = document.getElementById('seg-mill-in');
            if (existingMillIn) existingMillIn.remove();   // guard re-runs
            segContainer.insertAdjacentHTML('afterbegin',
                `<div id="seg-mill-in" class="flex justify-between px-4 py-3 border-b border-gray-100 text-sm hover:bg-gray-50 transition-colors">` +
                `<span class="text-gray-600 font-medium">Mill to Estate Entrance (Live API)</span>` +
                `<span class="font-bold text-blue-600">${googleDistKm.toFixed(2)} km</span></div>`);
        });
    }
}