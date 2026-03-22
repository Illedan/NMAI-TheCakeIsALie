We are working in /Users/erikkvanli/Repos/NMAI-TheCakeIsALi
e/astar-erik/CHALLENGE.md\  
 We have history here: /Users/erikkvanli/Repos/NMAI-TheCakeI  
 sALie/astar-island/replays\  
 And here: /Users/erikkvanli/Repos/NMAI-TheCakeIsALie/astar-  
 island/initial_states\  
 source /Users/erikkvanli/Repos/NMAI-TheCakeIsALie/astar-isl  
 and/.venv/bin/activate  
 You are NOT to do API calls now. In this new folder  
 astar-erik I want you to setup a C++ framework for this  
 task. We are to work on this locally. Replays are  
 downloaded replays that simulate 1 possible env of many in  
 this stocatic world.\  
 Simulations are the queries and responses, given the  
 initial_states

Analysis is the actual probability distribution that we should predict.

I need a local test setup that allows me to query which will get a snapshot from final state of the replays. And then in the end return a probability vector for each seed. And then a local score on how good that probability was. I need a contained C++ file with some infra.cpp files that has the framework. Model it in a way that we can turn it on online later with a flag, but don't add the code to accidentally use the API for now. I want the C++ code to do something random and query something random. It has 50 querries each game and has to submit 5 probability vectors. Check analysis folder and docs to see the actual format. And add a comment in my C++ file to indicate which of the probas are which (index consts)
Also from every run I want a file added to my view folder that is a HTML file. It should show the first frame to the left and guessed probas in the center and actual probas to the right. Have Green as correct guessed vs red as the worst possible guess (linear coloring based on how invalid it was)
Add tooltips in the viewer to be able to understand what I see. And a forth image on the right to most predicted tile.

- TLDR: 4 images for each seed: Initial, Guessed, Actual, Most Proba

Use infra.cpp and infra.h and solution.cpp as names.
