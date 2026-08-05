import { initMediaPipe, getFaceLandmarker } from "./mediapipe.js";

let running = false;
let lastVideoTime = -1;

let nervousness = 20;
let suspicion = 20;

export async function startFaceAnalysis() {

    console.log("Face Analysis Started");

    if (running) return;

    running = true;

    await initMediaPipe();

    const video = document.getElementById("defendant-video");

    const landmarker = getFaceLandmarker();

    async function detect(){

        if(!running){
            return;
        }

        if(video.readyState < 2){
            requestAnimationFrame(detect);
            return;
        }

        const now = performance.now();

        if(video.currentTime !== lastVideoTime){

            lastVideoTime = video.currentTime;

            const result = landmarker.detectForVideo(video, now);

            if(result.faceLandmarks.length > 0){

                analyse(result.faceLandmarks[0]);

            }

        }

        requestAnimationFrame(detect);

    }

    detect();

}

function analyse(points){

    console.log("analyse");

    const leftEye =
        distance(points[159],points[145]);

    const rightEye =
        distance(points[386],points[374]);

    const mouth =
        distance(points[13],points[14]);

    const faceTurn =
        Math.abs(points[234].x-points[454].x);

    //---------------------------------

    if(leftEye<0.012 && rightEye<0.012){

        nervousness+=2;

    }else{

        nervousness-=0.3;

    }

    if(mouth>0.05){

        nervousness+=0.5;

    }

    if(faceTurn<0.23){

        suspicion+=0.4;

    }else{

        suspicion-=0.2;

    }

    nervousness=Math.max(0,Math.min(100,nervousness));
    suspicion=Math.max(0,Math.min(100,suspicion));

    updateGauge();

}

function updateGauge(){

    document.getElementById("nervousness-fill").style.width=nervousness+"%";
    document.getElementById("nervousness-value").textContent=Math.round(nervousness)+"%";

    document.getElementById("suspicion-fill").style.width=suspicion+"%";
    document.getElementById("suspicion-value").textContent=Math.round(suspicion)+"%";

}

function distance(a,b){

    return Math.sqrt(

        (a.x-b.x)*(a.x-b.x)+
        (a.y-b.y)*(a.y-b.y)

    );

}

window.startFaceAnalysis = startFaceAnalysis;