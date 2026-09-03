from _dispatch import expose

expose(globals(), "data_engineer", "fetch_dataset.py")
if __name__ == "__main__":
    main()
