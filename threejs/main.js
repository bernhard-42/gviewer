import * as THREE from "three";
import { TrackballControls } from "three/addons/controls/TrackballControls.js";
import * as gds from "./gds.js";

function fromB64(s) {
    let bytes = atob(s);
    let uint = new Uint8Array(bytes.length);
    for (var i = 0; i < bytes.length; i++) uint[i] = bytes[i].charCodeAt(0);
    return uint;
}

function convert(obj) {
    var vectorArray = [];
    var buffer = fromB64(obj.buffer);
    if (obj.dtype === "float32") {
        var coords = new Float32Array(buffer.buffer);
        vectorArray = new Array(coords.length / 2);
        for (let i = 0, j = 0; i < coords.length; i += 2, j++) {
            vectorArray[j] = new THREE.Vector2(coords[i], coords[i + 1]);
        }
    } else {
        console.log("Error: unknown dtype", obj.dtype);
    }
    return vectorArray;
}

var t = performance.now();
for (var name in gds.gds.layers) {
    console.log(name);
    const layer = gds.gds.layers[name];
    for (var index in layer.polygons) {
        layer.polygons[index] = convert(layer.polygons[index]);
    }
}
console.log("Time to convert polygons:", performance.now() - t);

const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(
    75,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
);

const renderer = new THREE.WebGLRenderer();
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// const polygon1 = [
//     new THREE.Vector2(-0.2, -25),
//     new THREE.Vector2(-0.2, -15),
//     new THREE.Vector2(23.133, -15),
//     new THREE.Vector2(23.133, 5),
//     new THREE.Vector2(33.133, 5),
//     new THREE.Vector2(33.133, -15),
//     new THREE.Vector2(69.799, -15),
//     new THREE.Vector2(69.799, 5),
//     new THREE.Vector2(79.799, 5),
//     new THREE.Vector2(79.799, -15),
//     new THREE.Vector2(89.8, -15),
//     new THREE.Vector2(89.8, -25)
// ];

// const polygon2 = [
//     new THREE.Vector2(-0.2, -5),
//     new THREE.Vector2(-0.2, 25),
//     new THREE.Vector2(89.8, 25),
//     new THREE.Vector2(89.8, 15),
//     new THREE.Vector2(56.466, 15),
//     new THREE.Vector2(56.466, -5),
//     new THREE.Vector2(46.466, -5),
//     new THREE.Vector2(46.466, 15),
//     new THREE.Vector2(9.8, 15),
//     new THREE.Vector2(9.8, -5)
// ];

// Create Shape objects from the polygons
function createShape(points) {
    const shape = new THREE.Shape();
    shape.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
        shape.lineTo(points[i].x, points[i].y);
    }
    shape.closePath();
    return shape;
}

var shapes = [];
for (var key in gds.gds.layers) {
    const polygons = gds.gds.layers[key].polygons;
    for (var j = 0; j < polygons.length; j++) {
        const polygon = polygons[j];
        const shape = createShape(polygon);
        shapes.push(shape);
    }
}

// Extrude settings
const extrudeSettings = {
    depth: 2,
    bevelEnabled: false
};

// Geometry and mesh
const geometry = new THREE.ExtrudeGeometry(shapes, extrudeSettings);
const material = new THREE.MeshPhongMaterial({
    color: 0xadd8e6, // light blue
    side: THREE.DoubleSide,
    flatShading: true
});
const mesh = new THREE.Mesh(geometry, material);

// Edges
const edges = new THREE.EdgesGeometry(geometry);
const lineMaterial = new THREE.LineBasicMaterial({ color: 0x000000 }); // black
const edgesMesh = new THREE.LineSegments(edges, lineMaterial);

scene.add(mesh);
scene.add(edgesMesh);

// Lighting
const light = new THREE.DirectionalLight(0xffffff, 1);
light.position.set(50, 50, 100);
scene.add(light);
scene.add(new THREE.AmbientLight(0xffffff, 0.5));

camera.position.z = 2;

// Add TrackballControls
const controls = new TrackballControls(camera, renderer.domElement);

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}

animate();

// Handle resizing
window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    controls.handleResize(); // Update controls on resize[1]
});
